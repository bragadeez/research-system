"""
agents/search_agent.py

Multi-source search agent:
  - DuckDuckGo (web)
  - arXiv + Semantic Scholar (academic)
  - Wikipedia (general context)

Fixes applied:
  - _make_academic_source now uses proper async locking (no race condition)
  - Wikipedia query uses first 3 meaningful words (not just the first word)
  - MAX_RAW_SOURCES reads from settings
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Callable, List, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

from config import settings
from models.source import RawSource
from tools.scraper import content_hash, domain_score, fetch_page, query_score
from tools.search_tools import academic_search, search_duckduckgo, search_wikipedia

# Common stopwords to skip when building Wikipedia query
_WIKI_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about",
    "impact", "analysis", "research", "study", "report", "overview", "latest",
    "new", "advances", "findings", "recent", "current", "using", "based",
}


class SearchAgent:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(6)
        self.seen_urls: set = set()
        self.seen_hash: set = set()
        self.domain_count: dict = defaultdict(int)
        self.MAX_PER_DOMAIN: int = settings.MAX_PER_DOMAIN
        self.MAX_RAW_SOURCES: int = settings.MAX_RAW_SOURCES
        self._lock = asyncio.Lock()

    def _reset(self):
        self.seen_urls.clear()
        self.seen_hash.clear()
        self.domain_count.clear()

    def normalize_url(self, url: str) -> str:
        return url.split("#")[0].rstrip("/")

    async def _allow_domain(self, domain: str) -> bool:
        async with self._lock:
            if self.domain_count[domain] >= self.MAX_PER_DOMAIN:
                return False
            self.domain_count[domain] += 1
            return True

    async def _mark_url_seen(self, url: str) -> bool:
        async with self._lock:
            if url in self.seen_urls:
                return False
            self.seen_urls.add(url)
            return True

    async def _mark_hash_seen(self, h: str) -> bool:
        async with self._lock:
            if h in self.seen_hash:
                return False
            self.seen_hash.add(h)
            return True

    async def process_url(
        self, client: httpx.AsyncClient, result: dict, subtopic: str, query: str
    ) -> Optional[RawSource]:
        """Fetch a web URL, deduplicate, and score it."""
        url = self.normalize_url(result["url"])
        if not await self._mark_url_seen(url):
            return None

        async with self.semaphore:
            data = await fetch_page(client, url)

        if not data:
            return None

        content, fetch_time = data
        h = content_hash(content)
        if not await self._mark_hash_seen(h):
            return None

        try:
            domain = urlparse(url).netloc
        except Exception:
            domain = "unknown"

        if not await self._allow_domain(domain):
            return None

        return RawSource(
            url=url,
            title=result.get("title", ""),
            content=content,
            domain=domain,
            query=query,
            subtopic=subtopic,
            content_length=len(content),
            fetch_time=fetch_time,
            domain_score=domain_score(url),
            query_match_score=query_score(content, query),
            final_score=0.0,
        )

    async def _make_academic_source(
        self, result: dict, subtopic: str, query: str
    ) -> Optional[RawSource]:
        """
        Convert an academic result (arXiv / Semantic Scholar / Wikipedia)
        into a RawSource. Content is pre-populated — no HTTP fetch needed.
        Uses async locks to prevent race conditions on shared state.
        """
        url = self.normalize_url(result.get("url", ""))
        if not url:
            return None

        content = result.get("content") or result.get("snippet", "")
        if len(content) < 100:
            return None

        h = content_hash(content)
        if not await self._mark_hash_seen(h):
            return None
        if not await self._mark_url_seen(url):
            return None

        source_type = result.get("source", "academic")
        d_score = {
            "arxiv":            0.90,
            "semantic_scholar": 0.85,
            "wikipedia":        0.70,
        }.get(source_type, 0.75)

        try:
            domain = urlparse(url).netloc or source_type
        except Exception:
            domain = source_type

        return RawSource(
            url=url,
            title=result.get("title", ""),
            content=content,
            domain=domain,
            query=query,
            subtopic=subtopic,
            content_length=len(content),
            fetch_time=0.0,
            domain_score=d_score,
            query_match_score=query_score(content, query),
            final_score=0.0,
        )

    def _get_source_types(self, sub) -> List[str]:
        return [
            st.value if hasattr(st, "value") else str(st)
            for st in getattr(sub, "source_types", [])
        ]

    def _wiki_query(self, query: str) -> str:
        """Extract the 3 most meaningful words from a query for Wikipedia lookup."""
        tokens = [t for t in query.split() if t.lower() not in _WIKI_STOPWORDS and len(t) > 2]
        return " ".join(tokens[:3]) if tokens else query.split()[0]

    async def run(
        self,
        plan,
        progress_callback: Optional[Callable] = None,
    ) -> List[RawSource]:
        """
        Main search method — routes academic subtopics to arXiv + Semantic Scholar,
        general subtopics to DuckDuckGo + Wikipedia.
        """
        self._reset()
        sources: List[RawSource] = []
        web_url_jobs: List[tuple] = []
        academic_jobs: List[tuple] = []
        wiki_jobs: List[tuple] = []

        async def _notify(msg: str):
            if progress_callback:
                await progress_callback({"agent": "search", "message": msg, "data": {}})

        for sub in plan.subtopics:
            task_type = getattr(sub.task_type, "value", str(sub.task_type))
            if task_type != "research":
                continue

            source_types = self._get_source_types(sub)
            use_academic = "academic" in source_types
            use_web = not use_academic or any(
                st in source_types for st in ["news", "blog", "documentation", "industry_report"]
            )

            for query in sub.search_queries:
                if use_web:
                    query_variants = [query, f'"{query}"', f"{query} {plan.topic}"]
                    for q in query_variants:
                        try:
                            results = await asyncio.to_thread(search_duckduckgo, q, 5)
                            for r in results:
                                url = self.normalize_url(r["url"])
                                if url not in self.seen_urls:
                                    web_url_jobs.append((r, sub.title, q))
                        except Exception as exc:
                            logger.warning(f"[Search] DDG failed for '{q}': {exc}")

                if use_academic:
                    academic_jobs.append((query, sub.title))

                if not use_academic:
                    wiki_jobs.append((self._wiki_query(query), sub.title, query))

        await _notify(
            f"🔍 Searching: {len(web_url_jobs)} web URLs + "
            f"{len(academic_jobs)} academic queries…"
        )

        # ── 1. Academic sources (arXiv + Semantic Scholar) ────────────────────
        for query, subtopic in academic_jobs:
            try:
                academic_results = await academic_search(query, max_results=4)
                for r in academic_results:
                    src = await self._make_academic_source(r, subtopic, query)
                    if src:
                        sources.append(src)
                await asyncio.sleep(0.5)  # polite pause for S2 rate limits
            except Exception as exc:
                logger.warning(f"[Search] Academic search failed for '{query}': {exc}")

        # ── 2. Wikipedia context (capped at 3 calls) ──────────────────────────
        for wiki_q, subtopic, query in wiki_jobs[:3]:
            try:
                wiki_results = await asyncio.to_thread(search_wikipedia, wiki_q or query)
                for r in wiki_results:
                    src = await self._make_academic_source(r, subtopic, query)
                    if src:
                        sources.append(src)
            except Exception as exc:
                logger.debug(f"[Search] Wikipedia failed for '{wiki_q}': {exc}")

        # ── 3. Web scraping ───────────────────────────────────────────────────
        async with httpx.AsyncClient(timeout=20) as client:
            tasks = [self.process_url(client, r[0], r[1], r[2]) for r in web_url_jobs]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                logger.debug(f"[Search] Fetch error: {r}")
                continue
            if r:
                sources.append(r)

        total = len(sources)
        await _notify(f"✅ Search complete — {total} raw sources collected")
        logger.info(f"[SearchAgent] Total raw sources: {total}")
        return sources[: self.MAX_RAW_SOURCES]


search_agent = SearchAgent()
