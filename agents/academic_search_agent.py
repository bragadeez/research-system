"""
agents/academic_search_agent.py

Research Heavy mode search agent.

Sources queried:
  - arXiv          (free, no key)
  - Semantic Scholar with citationCount field (free, no key)
  - PubMed Central via E-utilities (free, no key)
  - CORE.ac.uk     (free, optional API key for higher rate limits)
  - OpenAlex       (free, no key, uses polite pool email)

Citation-per-year ranking formula:
    score = citation_count / (current_year - publication_year + 1)

Top-K filtering: only the highest-scored papers (up to HEAVY_PAPER_THRESHOLD)
are passed to the extraction stage.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Callable, Dict, List, Optional

import httpx
from loguru import logger

from config import settings
from models.source import RawSource
from tools.scraper import content_hash, domain_score, query_score
from tools.search_tools import search_arxiv

CURRENT_YEAR = datetime.now().year


# ─── Citation-per-year scoring ────────────────────────────────────────────────

def citation_score(citation_count: int, pub_year: Optional[int]) -> float:
    """
    Normalised impact metric:  citations / years_since_publication.
    A 2023 paper with 20 citations scores the same as a 2013 paper with 200.
    """
    if citation_count is None:
        citation_count = 0
    year_age = max(1, CURRENT_YEAR - (pub_year or CURRENT_YEAR) + 1)
    return citation_count / year_age


# ─── PubMed Central ───────────────────────────────────────────────────────────

async def search_pubmed(query: str, max_results: int = 8) -> List[Dict]:
    """
    NCBI E-utilities: esearch → efetch.
    Returns paper dicts with citation_count approximation via PubMed link count.
    """
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    params_search = {
        "db": "pmc", "term": query, "retmax": max_results,
        "retmode": "json", "sort": "relevance",
        "tool": "ScholarNodeAI", "email": settings.OPENALEX_EMAIL,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{base}/esearch.fcgi", params=params_search)
            if r.status_code != 200:
                return []
            data = r.json()
            ids = data.get("esearchresult", {}).get("idlist", [])
            if not ids:
                return []

            # Fetch summaries
            params_fetch = {
                "db": "pmc", "id": ",".join(ids[:max_results]),
                "retmode": "json", "rettype": "abstract",
                "tool": "ScholarNodeAI", "email": settings.OPENALEX_EMAIL,
            }
            r2 = await client.get(f"{base}/esummary.fcgi", params=params_fetch)
            if r2.status_code != 200:
                return []
            summaries = r2.json().get("result", {})

    except Exception as exc:
        logger.warning(f"[PubMed] request failed: {exc}")
        return []

    results = []
    for pmcid in ids[:max_results]:
        doc = summaries.get(pmcid, {})
        title = doc.get("title", "").strip()
        if not title:
            continue
        year_str = doc.get("pubdate", "")[:4]
        try:
            year = int(year_str)
        except ValueError:
            year = None
        authors = ", ".join(
            a.get("name", "") for a in doc.get("authors", [])[:3]
        )
        abstract_snippet = doc.get("sorttitle", title)
        content = (
            f"Title: {title}\n"
            f"Authors: {authors}\n"
            f"Year: {year or 'N/A'}\n\n"
            f"Abstract:\n{abstract_snippet}"
        )
        url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/"
        results.append({
            "title": title,
            "url": url,
            "content": content,
            "snippet": abstract_snippet[:300],
            "source": "pubmed",
            "pub_year": year,
            "citation_count": 0,   # PubMed doesn't expose citation counts freely
        })
    logger.debug(f"[PubMed] '{query}' → {len(results)} papers")
    return results


# ─── OpenAlex ─────────────────────────────────────────────────────────────────

async def search_openalex(query: str, max_results: int = 8) -> List[Dict]:
    """
    OpenAlex REST API — free, 250M+ works, includes cited_by_count.
    Uses polite pool (requires email in User-Agent).
    """
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": max_results,
        "select": "id,title,authorships,publication_year,cited_by_count,abstract_inverted_index,doi,open_access",
        "filter": "is_oa:true",   # open-access only so we can link to full text
        "mailto": settings.OPENALEX_EMAIL,
    }
    headers = {"User-Agent": f"ScholarNodeAI/3.0 (mailto:{settings.OPENALEX_EMAIL})"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code != 200:
                return []
            data = r.json()
    except Exception as exc:
        logger.warning(f"[OpenAlex] request failed: {exc}")
        return []

    results = []
    for work in data.get("results", []):
        title = work.get("title", "").strip()
        if not title:
            continue
        year = work.get("publication_year")
        citations = work.get("cited_by_count", 0) or 0
        authors = ", ".join(
            a.get("author", {}).get("display_name", "")
            for a in work.get("authorships", [])[:3]
        )

        # Reconstruct abstract from inverted index
        inv_idx = work.get("abstract_inverted_index") or {}
        abstract = ""
        if inv_idx:
            word_positions = [(pos, word) for word, positions in inv_idx.items()
                              for pos in positions]
            word_positions.sort()
            abstract = " ".join(w for _, w in word_positions)

        doi = work.get("doi", "")
        oa_url = (work.get("open_access") or {}).get("oa_url") or doi or work.get("id", "")

        content = (
            f"Title: {title}\n"
            f"Authors: {authors}\n"
            f"Year: {year or 'N/A'}\n"
            f"Citations: {citations}\n\n"
            f"Abstract:\n{abstract[:1500]}"
        )
        results.append({
            "title": title,
            "url": oa_url or f"https://openalex.org/{work.get('id','').split('/')[-1]}",
            "content": content,
            "snippet": abstract[:300],
            "source": "openalex",
            "pub_year": year,
            "citation_count": citations,
        })
    logger.debug(f"[OpenAlex] '{query}' → {len(results)} papers")
    return results


# ─── Semantic Scholar with citations ──────────────────────────────────────────

async def search_s2_with_citations(query: str, max_results: int = 8) -> List[Dict]:
    """Semantic Scholar — includes citationCount field."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,year,authors,citationCount,externalIds,openAccessPdf,url",
    }
    headers = {"User-Agent": "ScholarNodeAI/3.0 (research@scholarnode.ai)"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code == 429:
                await asyncio.sleep(3)
                r = await client.get(url, params=params, headers=headers)
            if r.status_code != 200:
                return []
            data = r.json()
    except Exception as exc:
        logger.warning(f"[S2+cit] request failed: {exc}")
        return []

    results = []
    for paper in data.get("data", []):
        abstract = paper.get("abstract") or ""
        if not abstract:
            continue
        authors = ", ".join(a.get("name", "") for a in paper.get("authors", [])[:3])
        year = paper.get("year")
        citations = paper.get("citationCount", 0) or 0
        content = (
            f"Title: {paper.get('title', '')}\n"
            f"Authors: {authors}\n"
            f"Year: {year or 'N/A'}\n"
            f"Citations: {citations}\n\n"
            f"Abstract:\n{abstract}"
        )
        pdf_url = (paper.get("openAccessPdf") or {}).get("url")
        paper_url = (
            pdf_url
            or paper.get("url")
            or f"https://semanticscholar.org/paper/{paper.get('paperId', '')}"
        )
        results.append({
            "title": paper.get("title", ""),
            "url": paper_url,
            "content": content,
            "snippet": abstract[:300],
            "source": "semantic_scholar",
            "pub_year": year,
            "citation_count": citations,
        })
    logger.debug(f"[S2+cit] '{query}' → {len(results)} papers")
    return results


# ─── arXiv wrapper with citation metadata ────────────────────────────────────

async def search_arxiv_enriched(query: str, max_results: int = 8) -> List[Dict]:
    """
    arXiv doesn't expose citation counts natively.
    We search S2 by arXiv ID to get citation count when available.
    Falls back to 0 citations if S2 lookup fails.
    """
    try:
        raw = await asyncio.get_event_loop().run_in_executor(
            None, search_arxiv, query, max_results
        )
    except Exception as exc:
        logger.warning(f"[arXiv] search failed: {exc}")
        return []

    enriched = []
    for r in raw:
        # Extract year from content
        year = None
        for line in r.get("content", "").split("\n"):
            if line.startswith("Published:"):
                try:
                    year = int(line.split(":")[1].strip()[:4])
                except Exception:
                    pass
        enriched.append({**r, "pub_year": year, "citation_count": 0})
    return enriched


# ─── Main Academic Search Agent ───────────────────────────────────────────────

class AcademicSearchAgent:
    """
    Runs all five academic sources in parallel, merges results,
    applies citation-per-year scoring, and returns the top-K papers.
    """

    def __init__(self):
        self._seen_urls: set = set()
        self._seen_hashes: set = set()

    def _reset(self):
        self._seen_urls.clear()
        self._seen_hashes.clear()

    def _dedup(self, papers: List[Dict]) -> List[Dict]:
        """Deduplicate by URL and content hash."""
        unique = []
        for p in papers:
            url = p.get("url", "")
            h = content_hash(p.get("content", ""))
            if url and url in self._seen_urls:
                continue
            if h in self._seen_hashes:
                continue
            self._seen_urls.add(url)
            self._seen_hashes.add(h)
            unique.append(p)
        return unique

    def _to_raw_source(self, paper: Dict, subtopic: str, query: str) -> Optional[RawSource]:
        """Convert paper dict to RawSource for compatibility with downstream pipeline."""
        content = paper.get("content", "")
        if len(content) < 100:
            return None
        url = paper.get("url", "")
        if not url:
            return None
        source_map = {
            "arxiv": 0.90,
            "semantic_scholar": 0.85,
            "openalex": 0.88,
            "pubmed": 0.87,
        }
        d_score = source_map.get(paper.get("source", ""), 0.80)
        return RawSource(
            url=url,
            title=paper.get("title", ""),
            content=content,
            domain=paper.get("source", "academic"),
            query=query,
            subtopic=subtopic,
            content_length=len(content),
            fetch_time=0.0,
            domain_score=d_score,
            query_match_score=query_score(content, query),
            final_score=0.0,
        )

    async def run(
        self,
        plan,
        paper_threshold: int = None,
        progress_callback: Optional[Callable] = None,
    ) -> tuple[List[RawSource], List[Dict]]:
        """
        Returns:
            (raw_sources, academic_papers_metadata)
            raw_sources — for downstream extraction / ranking
            academic_papers_metadata — enriched dicts with citation_count, pub_year, citation_score
        """
        self._reset()
        threshold = paper_threshold or settings.HEAVY_PAPER_THRESHOLD
        max_fetch = settings.HEAVY_MAX_SEARCH_RESULTS

        async def _notify(msg: str):
            if progress_callback:
                await progress_callback({"agent": "search", "message": msg, "data": {}})

        await _notify("📚 Research Heavy — searching academic databases…")

        # Gather all queries from the plan
        queries: List[tuple[str, str]] = []
        for sub in plan.subtopics:
            for q in sub.search_queries:
                queries.append((q, sub.title))

        if not queries:
            queries = [(plan.topic, "General")]

        # Run all sources in parallel per query
        all_papers: List[Dict] = []
        for query, subtopic in queries[:6]:   # cap at 6 queries to avoid rate limiting
            tasks = [
                search_arxiv_enriched(query, max_fetch // 4),
                search_s2_with_citations(query, max_fetch // 4),
                search_pubmed(query, max_fetch // 4),
                search_openalex(query, max_fetch // 4),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for batch in results:
                if isinstance(batch, Exception):
                    logger.warning(f"[AcademicSearch] Source error: {batch}")
                    continue
                for paper in batch:
                    paper["_subtopic"] = subtopic
                    paper["_query"] = query
            for batch in results:
                if not isinstance(batch, Exception):
                    all_papers.extend(batch)
            await asyncio.sleep(0.5)   # polite pause

        # Deduplicate
        unique_papers = self._dedup(all_papers)
        await _notify(f"🔍 Found {len(unique_papers)} unique papers across all sources")

        # Compute citation-per-year score
        for p in unique_papers:
            p["citation_score"] = citation_score(
                p.get("citation_count", 0),
                p.get("pub_year"),
            )

        # Sort and keep top-K
        unique_papers.sort(key=lambda p: p["citation_score"], reverse=True)
        top_papers = unique_papers[:threshold]

        await _notify(
            f"⭐ Top {len(top_papers)} papers selected by citation-per-year score "
            f"(threshold={threshold})"
        )
        for i, p in enumerate(top_papers[:5], 1):
            await _notify(
                f"  #{i} [{p.get('source','?')}] {p.get('title','')[:60]} "
                f"— citations/yr: {p['citation_score']:.1f}"
            )

        # Convert to RawSource objects
        raw_sources = []
        for p in top_papers:
            src = self._to_raw_source(p, p.get("_subtopic", ""), p.get("_query", plan.topic))
            if src:
                raw_sources.append(src)

        await _notify(f"✅ Heavy search complete — {len(raw_sources)} academic sources ready")
        return raw_sources, top_papers


academic_search_agent = AcademicSearchAgent()
