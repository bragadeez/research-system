"""
agents/extraction_agent.py

Evidence extraction using Groq (Llama 3.3 70B).
  - Batches up to PARA_BATCH_SIZE paragraphs per Groq call
  - Concurrent source processing via asyncio.gather + semaphore
  - Falls back to heuristic extraction if Groq call fails
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Callable, List, Optional, Set, Tuple

from loguru import logger

from core.llm_client import llm
from models.extraction import EvidenceCategory, ExtractedEvidence
from models.research_plan import ResearchPlan
from models.source import RankedSource


# ── Tuning constants ──────────────────────────────────────────────────────────
MAX_EVIDENCE_PER_SOURCE   = 10
MAX_PARAGRAPHS_PER_SOURCE = 6    # cap per source for speed
PARA_BATCH_SIZE           = 6    # paragraphs per Groq call
MIN_PARA_LEN              = 100
GROQ_CONCURRENCY          = 4    # concurrent Groq calls
MIN_KEEP_SCORE            = 0.26
MIN_TOPIC_SCORE           = 0.15

# ── Signal term sets ──────────────────────────────────────────────────────────
GENERAL_SIGNAL_TERMS = {
    "algorithm","algorithms","method","methods","model","models","framework",
    "frameworks","training","dataset","datasets","result","results","metric",
    "metrics","comparison","compare","compared","study","studies","evaluation",
    "experiment","experiments","benchmark","benchmarks","scalable","scalability",
    "distributed","parallel","performance","accuracy","efficiency","latency",
    "throughput","convergence","optimization","cost","time","speed",
}
MEDICAL_SIGNAL_TERMS = {
    "trial","trials","patient","patients","therapy","therapies","treatment",
    "treatments","drug","drugs","clinical","disease","diseases","cardiac",
    "cardiovascular","heart","stroke","blood","cholesterol","mortality",
    "safety","efficacy","outcome","outcomes","risk","risks","lipid","ejection",
    "fraction","gene","gene therapy","crispr",
}
BAD_PATTERNS = [
    "this article","this post","this section","this tutorial","this blog",
    "in this blog","in this tutorial","view pdf","sign up","subscribe",
    "cookie","accept cookies","related papers","references","bibliography",
    "acknowledgement","click here","read more","see also","table of contents",
    "downloads","login","register","advertisement","press release",
    "conflict of interest","funding statement","patent","copyright",
    "author information","corresponding author","affiliation",
    "endnote citation","bibtex",
]
MARKETING_WORDS = (
    "best","leading","world-class","state of the art","cutting-edge",
    "powerful solution","revolutionize","transform","unlock","seamless",
    "complete","ultimate","most complete",
)
QUESTION_STARTERS = (
    "what ","why ","how ","when ","where ","which ","who ","is ","are ",
    "can ","do ","does ",
)
DEFINITION_TERMS  = ["is defined as","defined as","refers to","means","is a","are a","can be described as","is the process of"]
METHOD_TERMS      = ["we propose","we present","we introduce","method","approach","framework","technique","procedure","pipeline","design","architecture","implementation"]
RESULT_TERMS      = ["result","results","shows","showed","demonstrates","demonstrated","finds","found","improves","improved","outperforms","outperformed","achieves","achieved","significantly","reduced","increased","lowered","raised"]
METRIC_TERMS      = ["%","accuracy","precision","recall","f1","latency","throughput","speedup","runtime","cost","error","loss","scaling","efficiency","reduction","survival","mortality"]
DATASET_TERMS     = ["dataset","datasets","corpus","benchmark","training set","test set","validation set","data set","sample","participants","patients"]
LIMITATION_TERMS  = ["limitation","limitations","challenge","challenges","bottleneck","trade-off","drawback","issue","problem","overhead","costly","hard to","difficult","fails","failure","uncertain","uncertainty","limited"]
COMPARISON_TERMS  = ["versus","vs","compared to","compares","comparison","better than","worse than","alternative","trade-off","among","between"]
TREND_TERMS       = ["trend","trends","growing","increasing","emerging","rapidly","future","evolving","adoption","popular"]
CONCLUSION_TERMS  = ["concludes","conclusion","overall","in summary","in conclusion","takeaway","takeaways"]


# ── Pure helpers ──────────────────────────────────────────────────────────────

def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())

def split_sentences(paragraph: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", paragraph)
    return [s.strip() for s in parts if s.strip()]

def split_paragraphs(text: str) -> List[str]:
    parts = re.split(r"\n{2,}", text)
    return [p.strip() for p in parts if p.strip()]

def make_evidence_id(key: str) -> str:
    return hashlib.md5(key.encode("utf-8", errors="ignore")).hexdigest()

def normalize_claim_key(claim: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", claim.lower()))[:60]

def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())

def is_declarative(sentence: str) -> bool:
    s = sentence.strip().lower()
    if s.startswith(QUESTION_STARTERS):
        return False
    if any(w in s for w in MARKETING_WORDS):
        return False
    return len(sentence) >= 30

def information_density(sentence: str, topic_tokens: set, signal_terms: set) -> bool:
    s_tokens = set(tokenize(sentence))
    return bool(s_tokens & signal_terms) or bool(s_tokens & topic_tokens)

def sentence_to_category(sentence: str) -> EvidenceCategory:
    s = sentence.lower()
    if any(t in s for t in DEFINITION_TERMS):  return EvidenceCategory.definition
    if any(t in s for t in METHOD_TERMS):       return EvidenceCategory.method
    if any(t in s for t in METRIC_TERMS):       return EvidenceCategory.metric
    if any(t in s for t in RESULT_TERMS):       return EvidenceCategory.result
    if any(t in s for t in DATASET_TERMS):      return EvidenceCategory.dataset
    if any(t in s for t in LIMITATION_TERMS):   return EvidenceCategory.limitation
    if any(t in s for t in COMPARISON_TERMS):   return EvidenceCategory.comparison
    if any(t in s for t in TREND_TERMS):        return EvidenceCategory.trend
    if any(t in s for t in CONCLUSION_TERMS):   return EvidenceCategory.conclusion
    return EvidenceCategory.context

def sentence_strength(sentence, topic_tokens, source_subtopic, topic) -> float:
    tokens = set(tokenize(sentence))
    all_relevant = topic_tokens | set(tokenize(topic)) | set(tokenize(source_subtopic))
    if not all_relevant:
        return 0.0
    overlap      = len(tokens & all_relevant) / max(len(all_relevant), 1)
    has_numeric  = 0.10 if re.search(r"\d", sentence) else 0.0
    length_bonus = min(0.10, len(sentence) / 500)
    return min(1.0, overlap + has_numeric + length_bonus)

def infer_domain_mode(topic: str) -> str:
    t = topic.lower()
    medical = {"cardio","cardiac","heart","clinical","trial","patient","disease","therapy","medicine","medical","stroke"}
    return "medical" if any(m in t for m in medical) else "general"

def signal_terms_for_topic(topic: str) -> Set[str]:
    mode = infer_domain_mode(topic)
    return GENERAL_SIGNAL_TERMS | MEDICAL_SIGNAL_TERMS if mode == "medical" else GENERAL_SIGNAL_TERMS

def category_bonus(category: EvidenceCategory) -> float:
    return {
        EvidenceCategory.definition: 0.06, EvidenceCategory.method: 0.08,
        EvidenceCategory.algorithm:  0.10, EvidenceCategory.result: 0.12,
        EvidenceCategory.metric:     0.12, EvidenceCategory.dataset: 0.06,
        EvidenceCategory.limitation: 0.08, EvidenceCategory.comparison: 0.08,
        EvidenceCategory.trend:      0.05, EvidenceCategory.conclusion: 0.05,
        EvidenceCategory.context:    0.02, EvidenceCategory.unknown: 0.00,
    }[category]

def _textify(value) -> str:
    if value is None: return ""
    if isinstance(value, str): return value
    if isinstance(value, list): return " ".join(_textify(v) for v in value)
    if hasattr(value, "value"): return str(value.value)
    return str(value)

def build_topic_profile(plan: ResearchPlan) -> Tuple[str, set]:
    parts = [_textify(plan.topic), _textify(plan.thesis),
             _textify(plan.contradictions_to_watch), _textify(plan.success_criteria)]
    for sub in plan.subtopics:
        parts.append(" ".join([
            _textify(getattr(sub, "title", "")),
            _textify(getattr(sub, "objective", "")),
            _textify(getattr(sub, "search_queries", [])),
            _textify(getattr(sub, "expected_evidence", [])),
        ]))
    profile_text = normalize_space(" ".join(parts))
    return profile_text, set(tokenize(profile_text))

def _groq_category_to_enum(cat_str: str) -> EvidenceCategory:
    mapping = {
        "result":     EvidenceCategory.result,
        "method":     EvidenceCategory.method,
        "metric":     EvidenceCategory.metric,
        "limitation": EvidenceCategory.limitation,
        "comparison": EvidenceCategory.comparison,
        "trend":      EvidenceCategory.trend,
        "definition": EvidenceCategory.definition,
        "conclusion": EvidenceCategory.conclusion,
        "algorithm":  EvidenceCategory.algorithm,
        "dataset":    EvidenceCategory.dataset,
    }
    return mapping.get(cat_str.lower().strip(), EvidenceCategory.unknown)


# ── ExtractionAgent ───────────────────────────────────────────────────────────

class ExtractionAgent:
    def __init__(self, max_evidence_per_source: int = MAX_EVIDENCE_PER_SOURCE):
        self.max_evidence_per_source = max_evidence_per_source
        self._sem = asyncio.Semaphore(GROQ_CONCURRENCY)

    # ── Groq-powered batch extraction ─────────────────────────────────────────

    async def _extract_with_groq(
        self,
        source: RankedSource,
        topic: str,
        paragraphs: List[str],
    ) -> List[ExtractedEvidence]:
        """Process an entire source in 1-2 Groq calls (batched paragraphs)."""
        results: List[ExtractedEvidence] = []

        for batch_start in range(0, len(paragraphs), PARA_BATCH_SIZE):
            batch = paragraphs[batch_start: batch_start + PARA_BATCH_SIZE]

            async with self._sem:
                try:
                    raw_items = await llm.extract_evidence_async(batch, topic, source.title)
                except Exception as e:
                    logger.debug(f"[Extraction] Gemini batch call failed: {e}")
                    raw_items = []

            for item in raw_items:
                claim = str(item.get("claim", "")).strip()
                if len(claim) < 20:
                    continue

                cat_str  = str(item.get("category", "unknown"))
                category = _groq_category_to_enum(cat_str)
                base_conf = float(item.get("confidence", 0.5))
                para_idx  = int(item.get("para", 1)) - 1

                source_boost = source.final_score
                if getattr(source, "source_kind", "unknown") in {"academic", "documentation", "government"}:
                    source_boost = min(1.0, source_boost + 0.05)

                confidence = min(1.0, (0.46 * source_boost) + (0.34 * base_conf) + category_bonus(category))
                if confidence < MIN_KEEP_SCORE:
                    continue

                keywords = [t for t in (GENERAL_SIGNAL_TERMS | MEDICAL_SIGNAL_TERMS) if t in claim.lower()]
                if not keywords:
                    keywords = [tok for tok in tokenize(claim) if len(tok) > 6][:8]

                evidence_id = make_evidence_id(
                    f"{source.url}|{source.subtopic}|{category.value}|{normalize_claim_key(claim)}"
                )

                results.append(ExtractedEvidence(
                    evidence_id=evidence_id,
                    topic=topic,
                    subtopic=source.subtopic,
                    source_url=source.url,
                    source_title=source.title,
                    domain=source.domain,
                    source_kind=getattr(source, "source_kind", "unknown"),
                    category=category,
                    claim=claim[:420],
                    evidence_text=batch[para_idx][:600] if para_idx < len(batch) else claim,
                    confidence=confidence,
                    source_score=source.final_score,
                    sentence_index=0,
                    paragraph_index=batch_start + para_idx,
                    support_count=1,
                    supporting_sources=[source.url],
                    keywords=keywords,
                ))

                if len(results) >= self.max_evidence_per_source:
                    return results

        return results

    # ── Heuristic extraction (fallback) ───────────────────────────────────────

    def _candidate_evidence(
        self,
        topic: str,
        topic_profile_tokens: set,
        signal_terms: set,
        source: RankedSource,
        paragraph: str,
        paragraph_index: int,
    ) -> List[ExtractedEvidence]:
        candidates: List[ExtractedEvidence] = []
        for sentence_index, sentence in enumerate(split_sentences(paragraph)):
            sentence = normalize_space(sentence)
            if not is_declarative(sentence):
                continue
            if not information_density(sentence, topic_profile_tokens, signal_terms):
                continue

            category = sentence_to_category(sentence)
            strength = sentence_strength(sentence, topic_profile_tokens, source.subtopic, topic)
            if strength < MIN_TOPIC_SCORE:
                continue
            if len(sentence) < 45 and category in {EvidenceCategory.context, EvidenceCategory.unknown}:
                continue

            claim = sentence[:420].strip()
            claim_key = normalize_claim_key(claim)
            if not claim_key:
                continue

            source_boost = source.final_score
            if getattr(source, "source_kind", "unknown") in {"academic", "documentation", "government"}:
                source_boost = min(1.0, source_boost + 0.05)
            if infer_domain_mode(topic) == "medical" and getattr(source, "source_kind", "unknown") == "academic":
                source_boost = min(1.0, source_boost + 0.05)

            confidence = min(1.0, (0.46 * source_boost) + (0.34 * strength) + category_bonus(category))
            if confidence < MIN_KEEP_SCORE:
                continue

            keywords = [t for t in (GENERAL_SIGNAL_TERMS | MEDICAL_SIGNAL_TERMS) if t in sentence.lower()]
            if not keywords:
                keywords = [tok for tok in tokenize(sentence) if len(tok) > 6][:8]

            candidates.append(ExtractedEvidence(
                evidence_id=make_evidence_id(
                    f"{source.url}|{source.subtopic}|{category.value}|{claim_key}"
                ),
                topic=topic,
                subtopic=source.subtopic,
                source_url=source.url,
                source_title=source.title,
                domain=source.domain,
                source_kind=getattr(source, "source_kind", "unknown"),
                category=category,
                claim=claim,
                evidence_text=sentence,
                confidence=confidence,
                source_score=source.final_score,
                sentence_index=sentence_index,
                paragraph_index=paragraph_index,
                support_count=1,
                supporting_sources=[source.url],
                keywords=keywords,
            ))
            if len(candidates) >= self.max_evidence_per_source:
                break
        return candidates

    def _aggregate_evidence(self, evidence_items: List[ExtractedEvidence]) -> List[ExtractedEvidence]:
        grouped: dict = {}
        for item in evidence_items:
            group_key = f"{item.topic}|{item.subtopic}|{item.category.value}|{normalize_claim_key(item.claim)}"
            grouped.setdefault(group_key, []).append(item)

        merged: List[ExtractedEvidence] = []
        for items in grouped.values():
            if not items:
                continue
            items = sorted(items, key=lambda x: (x.confidence, x.source_score, len(x.evidence_text)), reverse=True)
            primary = items[0]

            unique_sources, seen_sources = [], set()
            for item in items:
                for url in item.supporting_sources or [item.source_url]:
                    if url not in seen_sources:
                        seen_sources.add(url)
                        unique_sources.append(url)

            avg_confidence  = sum(x.confidence for x in items) / len(items)
            best_confidence = items[0].confidence
            source_score    = max(x.source_score for x in items)
            source_kinds    = {x.source_kind for x in items if x.source_kind}
            support_count   = len(unique_sources)

            merged_confidence = min(1.0,
                (0.38 * best_confidence) + (0.22 * avg_confidence) + (0.20 * source_score)
                + min(0.16, 0.04 * max(support_count - 1, 0))
                + min(0.08, 0.02 * max(len(source_kinds) - 1, 0))
                + (0.05 if infer_domain_mode(primary.topic) == "medical" else 0.0)
                + (0.05 if any(re.search(r"\d", x.claim) for x in items) else 0.0)
                + (0.08 if any(x.source_kind in {"academic", "documentation", "government"} for x in items) else 0.0),
            )

            claim_variants, seen_claims, keywords, seen_kw = [], set(), [], set()
            for item in items:
                ck = normalize_claim_key(item.claim)
                if ck and ck not in seen_claims:
                    seen_claims.add(ck)
                    claim_variants.append(item.claim)
                for kw in item.keywords:
                    if kw not in seen_kw:
                        seen_kw.add(kw)
                        keywords.append(kw)

            merged.append(ExtractedEvidence(
                evidence_id=make_evidence_id(
                    f"{primary.topic}|{primary.subtopic}|{primary.category.value}|{normalize_claim_key(primary.claim)}"
                ),
                topic=primary.topic,
                subtopic=primary.subtopic,
                source_url=primary.source_url,
                source_title=primary.source_title,
                domain=primary.domain,
                source_kind=primary.source_kind,
                category=primary.category,
                claim=primary.claim[:140].strip(),
                evidence_text=" ".join(claim_variants[:2]).strip() or primary.evidence_text,
                confidence=merged_confidence,
                source_score=source_score,
                sentence_index=primary.sentence_index,
                paragraph_index=primary.paragraph_index,
                support_count=support_count,
                supporting_sources=unique_sources,
                keywords=keywords[:10],
            ))

        merged.sort(key=lambda x: (x.confidence, x.support_count, x.source_score), reverse=True)
        return merged

    # ── Main run ──────────────────────────────────────────────────────────────

    async def run(
        self,
        plan: ResearchPlan,
        ranked_sources: List[RankedSource],
        progress_callback: Optional[Callable] = None,
    ) -> List[ExtractedEvidence]:
        topic = plan.topic
        _, topic_profile_tokens = build_topic_profile(plan)
        signal_terms = signal_terms_for_topic(topic)

        async def _notify(msg: str):
            if progress_callback:
                await progress_callback({"agent": "extraction", "message": msg, "data": {}})

        await _notify(
            f"🔬 Extracting from {len(ranked_sources)} sources (Groq Llama 3.3 70B)…"
        )

        async def _process_source(source: RankedSource) -> List[ExtractedEvidence]:
            raw_paragraphs = split_paragraphs(source.content)
            good_paragraphs = []
            for p in raw_paragraphs:
                p = normalize_space(p)
                if not p or len(p) < MIN_PARA_LEN:
                    continue
                if any(bp in p.lower() for bp in BAD_PATTERNS):
                    continue
                good_paragraphs.append(p)
                if len(good_paragraphs) >= MAX_PARAGRAPHS_PER_SOURCE:
                    break

            if not good_paragraphs:
                return []

            # Try Groq extraction; fall back to heuristics if it fails
            items = await self._extract_with_groq(source, topic, good_paragraphs)
            if not items:
                logger.debug(f"[Extraction] Groq returned nothing for '{source.title[:50]}', using heuristics")
                items = []
                for pi, para in enumerate(good_paragraphs):
                    items.extend(self._candidate_evidence(
                        topic, topic_profile_tokens, signal_terms, source, para, pi
                    ))

            return items[:self.max_evidence_per_source]

        # Concurrent processing (semaphore inside limits Groq pressure)
        source_tasks = [_process_source(src) for src in ranked_sources]
        results_per_source = await asyncio.gather(*source_tasks, return_exceptions=True)

        raw_candidates: List[ExtractedEvidence] = []
        for res in results_per_source:
            if isinstance(res, Exception):
                logger.debug(f"[Extraction] Source processing error: {res}")
            elif res:
                raw_candidates.extend(res)

        deduped = self._aggregate_evidence(raw_candidates)
        logger.info(
            f"[Extraction] Raw: {len(raw_candidates)} → Deduped: {len(deduped)} "
            f"from {len(ranked_sources)} sources"
        )

        await _notify(f"✅ Extracted {len(deduped)} evidence items from {len(ranked_sources)} sources")
        return deduped


extraction_agent = ExtractionAgent()
