"""
core/source_ranker.py

Your original source_ranker.py — fully preserved.
No logic changes. Fixed only the import path to match new project layout.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from loguru import logger

from models.research_plan import ResearchIntent, ResearchPlan, SourceType
from models.source import RawSource, RankedSource

try:
    from sentence_transformers import SentenceTransformer, util
except Exception:
    SentenceTransformer = None
    util = None


TRACKING_PARAMS = {
    "gclid", "fbclid", "igshid", "mc_cid", "mc_eid", "mkt_tok",
    "ref", "ref_src", "utm_campaign", "utm_content", "utm_medium",
    "utm_source", "utm_term",
}

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about",
    "your", "you", "are", "was", "were", "been", "will", "would", "shall",
    "have", "has", "had", "not", "but", "can", "could", "may", "might",
    "what", "which", "when", "where", "why", "how", "who", "whom", "whose",
    "impact", "analysis", "research", "study", "report", "overview",
    "article", "blog", "guide", "intro", "introduction", "latest", "new",
}

HIGH_TRUST_PATTERNS = (
    ".gov", ".edu", "arxiv.org", "pubmed.ncbi.nlm.nih.gov",
    "nature.com", "science.org", "sciencedirect.com", "ieee.org",
    "acm.org", "springer.com", "wiley.com", "cell.com", "thelancet.com",
    "reuters.com", "apnews.com", "bbc.com", "ft.com", "bloomberg.com",
)

DOCUMENTATION_PATTERNS = (
    "docs.", "/docs", "/documentation", "/api", "/guide", "/tutorial",
    "developer.", "developers.", "learn.microsoft.com", "tensorflow.org",
    "pytorch.org", "huggingface.co", "colossalai.org",
)

BLOG_PATTERNS = (
    "medium.com", "towardsai.net", "towardsdatascience.com",
    "substack.com", "/blog/", "/posts/",
)

NEWS_PATTERNS = (
    "reuters.com", "apnews.com", "bbc.com", "ft.com",
    "bloomberg.com", "wsj.com", "nytimes.com", "theverge.com",
)

REPORT_PATTERNS = (
    "whitepaper", "report", "insights", "research", "case-study", "case study",
)

FORUM_PATTERNS = (
    "reddit", "quora", "stackoverflow", "stackexchange", "forum",
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _textify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_textify(v) for v in value)
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def tokenize(text: str) -> List[str]:
    return [
        token for token in re.findall(r"[a-z0-9]+", _textify(text).lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


def extract_phrases(text: str, min_n: int = 2, max_n: int = 3, limit: int = 12) -> List[str]:
    tokens = tokenize(text)
    phrases: List[str] = []
    seen = set()
    for n in range(max_n, min_n - 1, -1):
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(tokens[i: i + n])
            if phrase in seen:
                continue
            seen.add(phrase)
            phrases.append(phrase)
            if len(phrases) >= limit:
                return phrases
    return phrases


def normalize_url(url: str) -> str:
    if not url:
        return url
    parts = urlsplit(url)
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query_pairs.sort()
    path = parts.path.rstrip("/") or parts.path
    normalized = urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        path,
        "&".join(f"{k}={v}" for k, v in query_pairs),
        "",
    ))
    return normalized.rstrip("/")


def domain_from_url(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower()
    except Exception:
        return "unknown"


@dataclass
class TextProfile:
    text: str
    tokens: set
    phrases: List[str]


class SourceRanker:
    def __init__(
        self,
        embedding_model: str = None,
        min_score: float = 0.40,
        max_results: int = 30,
        use_embeddings: bool = True,
    ):
        from config import settings
        self.embedding_model = embedding_model or settings.EMBEDDING_MODEL
        self.min_score = min_score
        self.max_results = max_results
        self.use_embeddings = use_embeddings
        self._embedder = None

    @property
    def embedder(self):
        if not self.use_embeddings or SentenceTransformer is None:
            return None
        if self._embedder is None:
            try:
                self._embedder = SentenceTransformer(self.embedding_model)
            except Exception as exc:
                logger.warning(f"[SourceRanker] Embedding model failed: {exc}")
                self._embedder = None
        return self._embedder

    def _profile(self, text: str, phrase_limit: int = 12) -> TextProfile:
        text = _textify(text)
        return TextProfile(
            text=text,
            tokens=set(tokenize(text)),
            phrases=extract_phrases(text, limit=phrase_limit),
        )

    def _infer_intent(self, topic: str, plan: Optional[ResearchPlan]) -> str:
        if plan and getattr(plan, "research_intent", None):
            return _textify(plan.research_intent)
        t = _textify(topic).lower()
        if any(k in t for k in ["compare", "comparison", "versus", "v/s", "difference"]):
            return "comparison"
        if any(k in t for k in ["market", "industry", "revenue", "forecast", "adoption"]):
            return "market_analysis"
        if any(k in t for k in ["trend", "future", "emerging", "roadmap"]):
            return "trend_analysis"
        if any(k in t for k in ["impact", "effect", "influence", "jobs", "workforce"]):
            return "impact_analysis"
        return "technical_research"

    def _build_plan_text(self, topic: str, plan: Optional[ResearchPlan]) -> str:
        pieces = [topic]
        if not plan:
            return " ".join(pieces)
        pieces.extend([
            _textify(plan.thesis),
            _textify(plan.audience),
            _textify(plan.complexity),
            _textify(plan.core_tasks),
            _textify(plan.optional_tasks),
            _textify(plan.execution_order),
            _textify(plan.contradictions_to_watch),
            _textify(plan.success_criteria),
            _textify(plan.source_strategy),
        ])
        for section in getattr(plan, "sections", []) or []:
            pieces.extend([
                _textify(getattr(section, "title", "")),
                _textify(getattr(section, "purpose", "")),
            ])
        for sub in getattr(plan, "subtopics", []) or []:
            pieces.extend([
                _textify(getattr(sub, "title", "")),
                _textify(getattr(sub, "objective", "")),
                _textify(getattr(sub, "search_queries", [])),
                _textify(getattr(sub, "expected_evidence", [])),
            ])
        return " ".join(pieces)

    def _alignment_score(self, profile: TextProfile, source: RawSource) -> float:
        source_text = f"{source.title} {source.content[:3000]}"
        source_tokens = set(tokenize(source_text))

        if not profile.tokens:
            return 0.0

        token_overlap = len(profile.tokens & source_tokens) / max(len(profile.tokens), 1)

        phrase_hits = sum(1 for p in profile.phrases if p in source_text.lower())
        phrase_score = min(1.0, phrase_hits / max(len(profile.phrases), 1))

        if self.embedder and util is not None:
            try:
                v1 = self.embedder.encode(profile.text[:500], normalize_embeddings=True)
                v2 = self.embedder.encode(source_text[:500], normalize_embeddings=True)
                embed_score = float(util.cos_sim(v1, v2).item())
                return _clamp(0.40 * token_overlap + 0.20 * phrase_score + 0.40 * embed_score)
            except Exception:
                pass

        return _clamp(0.60 * token_overlap + 0.40 * phrase_score)

    def _infer_source_kind(self, source: RawSource) -> str:
        url = source.url.lower()
        if any(p in url for p in FORUM_PATTERNS):
            return "forum"
        if any(p in url for p in NEWS_PATTERNS):
            return "news"
        if any(p in url for p in BLOG_PATTERNS):
            return "blog"
        if any(p in url for p in REPORT_PATTERNS):
            return "industry_report"
        if any(p in url for p in HIGH_TRUST_PATTERNS):
            if ".gov" in url:
                return "government"
            if ".edu" in url or "arxiv.org" in url:
                return "academic"
            return "documentation"
        if any(p in url for p in DOCUMENTATION_PATTERNS):
            return "documentation"
        # Check content-based hints
        content_lower = source.content[:500].lower()
        if any(p in content_lower for p in REPORT_PATTERNS):
            return "industry_report"
        if "arxiv" in url or "semantic" in url:
            return "academic"
        if ".edu" in url or "arxiv.org" in url:
            return "academic"
        return "documentation" if any(p in url for p in DOCUMENTATION_PATTERNS) else "unknown"

    def _intent_prior(self, intent: str, source_kind: str) -> float:
        priors = {
            "technical_research": {
                "academic": 0.92, "documentation": 0.90, "government": 0.82,
                "news": 0.70, "industry_report": 0.76, "blog": 0.56,
                "forum": 0.34, "unknown": 0.52,
            },
            "comparison": {
                "academic": 0.86, "documentation": 0.84, "government": 0.78,
                "news": 0.74, "industry_report": 0.76, "blog": 0.58,
                "forum": 0.34, "unknown": 0.50,
            },
            "market_analysis": {
                "academic": 0.68, "documentation": 0.72, "government": 0.74,
                "news": 0.88, "industry_report": 0.86, "blog": 0.60,
                "forum": 0.30, "unknown": 0.54,
            },
            "trend_analysis": {
                "academic": 0.72, "documentation": 0.76, "government": 0.74,
                "news": 0.88, "industry_report": 0.84, "blog": 0.64,
                "forum": 0.30, "unknown": 0.54,
            },
            "impact_analysis": {
                "academic": 0.76, "documentation": 0.76, "government": 0.80,
                "news": 0.84, "industry_report": 0.76, "blog": 0.58,
                "forum": 0.30, "unknown": 0.54,
            },
        }
        return priors.get(intent, priors["technical_research"]).get(source_kind, 0.52)

    def _plan_source_bias(self, source_kind: str, plan: Optional[ResearchPlan]) -> float:
        if not plan or not getattr(plan, "source_strategy", None):
            return 0.0
        desired = {_textify(x).lower().strip() for x in plan.source_strategy}
        mapped = source_kind if source_kind != "forum" else "blog"
        if mapped in desired:
            return 0.08
        if source_kind in {"blog", "forum"} and ("academic" in desired or "documentation" in desired):
            return -0.04
        return 0.0

    def _credibility_score(self, source: RawSource, intent: str, source_kind: str,
                           plan: Optional[ResearchPlan]) -> float:
        intent_prior = self._intent_prior(intent, source_kind)
        plan_bias = self._plan_source_bias(source_kind, plan)
        domain_prior = _clamp(source.domain_score)
        score = (0.55 * intent_prior) + (0.30 * domain_prior) + (0.15 * (intent_prior + plan_bias))
        return _clamp(score)

    def _quality_flags(self, source: RawSource, source_kind: str, topic_alignment: float,
                       relevance_score: float, final_score: float) -> List[str]:
        flags: List[str] = []
        if source_kind in {"academic", "documentation", "government"}:
            flags.append("high_trust_kind")
        if source.content_length < 1200:
            flags.append("short_content")
        if source.content_length > 7000:
            flags.append("long_form")
        if source.query_match_score >= 65:
            flags.append("strong_query_match")
        if topic_alignment < 0.18:
            flags.append("weak_topic_fit")
        if topic_alignment >= 0.55:
            flags.append("strong_topic_focus")
        if relevance_score >= 0.70:
            flags.append("strong_relevance")
        if final_score >= 0.80:
            flags.append("high_confidence")
        return flags

    def score_source(self, source: RawSource, topic_profile: TextProfile,
                     plan_profile: TextProfile, intent: str,
                     plan: Optional[ResearchPlan] = None) -> RankedSource:
        source_kind = self._infer_source_kind(source)
        topic_alignment = self._alignment_score(topic_profile, source)
        plan_alignment = self._alignment_score(plan_profile, source) if plan_profile.text else topic_alignment
        relevance_score = _clamp((0.70 * topic_alignment) + (0.30 * plan_alignment))
        credibility_score = self._credibility_score(source, intent, source_kind, plan)
        query_support = _clamp(source.query_match_score / 100.0)
        length_score = _clamp(source.content_length / 12000.0)

        final_score = _clamp(
            (0.55 * relevance_score) + (0.22 * credibility_score)
            + (0.13 * query_support) + (0.10 * length_score)
        )

        if topic_alignment < 0.15:
            final_score *= 0.88
        if source_kind == "forum":
            final_score *= 0.85
        if intent == "technical_research" and source_kind == "blog" and relevance_score < 0.45:
            final_score *= 0.92

        final_score = _clamp(final_score)

        flags = self._quality_flags(source, source_kind, topic_alignment, relevance_score, final_score)
        reason = (
            f"kind={source_kind}, topic_alignment={topic_alignment:.3f}, "
            f"plan_alignment={plan_alignment:.3f}, credibility={credibility_score:.3f}, "
            f"query={query_support:.3f}, length={length_score:.3f}"
        )

        data = source.model_dump()
        data.pop("final_score", None)

        return RankedSource(
            **data,
            normalized_url=normalize_url(source.url),
            source_kind=source_kind,
            topic_alignment=topic_alignment,
            credibility_score=credibility_score,
            relevance_score=relevance_score,
            length_score=length_score,
            final_score=final_score,
            quality_flags=flags,
            rank_reason=reason,
        )

    def rank_sources(
        self,
        sources: Iterable[RawSource],
        topic: str,
        plan: Optional[ResearchPlan] = None,
        min_score: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[RankedSource]:
        threshold = self.min_score if min_score is None else min_score
        max_items = self.max_results if limit is None else limit

        topic_profile = self._profile(topic, phrase_limit=10)
        plan_text = self._build_plan_text(topic, plan)
        plan_profile = self._profile(plan_text, phrase_limit=16)
        intent = self._infer_intent(topic, plan)

        ranked: List[RankedSource] = []
        for source in sources:
            if not source.content:
                continue
            scored = self.score_source(source, topic_profile, plan_profile, intent, plan)
            ranked.append(scored)

        ranked.sort(
            key=lambda s: (s.final_score, s.topic_alignment, s.credibility_score, s.relevance_score, s.content_length),
            reverse=True,
        )

        filtered = [s for s in ranked if s.final_score >= threshold]
        if not filtered and ranked:
            filtered = ranked[: min(max_items, len(ranked))]

        return filtered[:max_items]


source_ranker = SourceRanker()
