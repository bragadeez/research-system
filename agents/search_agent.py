"""
agents/search_agent.py

Improvements vs original:
  1. Academic routing: subtopics with source_type=academic → arXiv + Semantic Scholar
  2. Wikipedia added for general context
  3. Progress callback support for streaming UI
  4. All original class methods preserved with same names
  5. Pre-populated content for academic sources (no scraping needed)
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Callable, List, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

from models.source import RawSource
from tools.scraper import content_hash, domain_score, fetch_page, query_score
from tools.search_tools import (
    academic_search,
    search_duckduckgo,
    search_wikipedia,
)


class SearchAgent:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(6)
        self.seen_urls: set = set()
        self.seen_hash: set = set()
        self.domain_count: dict = defaultdict(int)
        self.MAX_PER_DOMAIN = 3
        self.MAX_RAW_SOURCES = 60
        self._lock = asyncio.Lock()

    def _reset(self):
        """Reset state between runs."""
        self.seen_urls.clear()
        self.seen_hash.clear()
        self.domain_count.clear()

    def normalize_url(self, url: str) -> str:
        url = url.split("#")[0]
        return url.rstrip("/")

    async def allow_domain(self, domain: str) -> bool:
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

    async def process_url(self, client: httpx.AsyncClient, result: dict, subtopic: str, query: str) -> Optional[RawSource]:
        """Process a web URL — fetch, deduplicate, score."""
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

        if not await self.allow_domain(domain):
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

    def _make_academic_source(self, result: dict, subtopic: str, query: str) -> Optional[RawSource]:
        """
        Convert an academic search result (arXiv / Semantic Scholar / Wikipedia)
        into a RawSource. No HTTP fetch needed — content is already in the result.
        """
        url = self.normalize_url(result.get("url", ""))
        if not url:
            return None

        content = result.get("content") or result.get("snippet", "")
        if len(content) < 100:
            return None

        h = content_hash(content)
        if h in self.seen_hash:
            return None
        self.seen_hash.add(h)

        if url in self.seen_urls:
            return None
        self.seen_urls.add(url)

        source_type = result.get("source", "academic")
        # Academic sources get a high domain_score bonus
        d_score = {
            "arxiv": 0.90,
            "semantic_scholar": 0.85,
            "wikipedia": 0.70,
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

    async def run(
        self,
        plan,
        progress_callback: Optional[Callable] = None,
    ) -> List[RawSource]:
        """
        Main search method — same signature as original plus optional callback.
        Automatically routes academic subtopics to arXiv + Semantic Scholar.
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
                # Web search jobs
                if use_web:
                    # Expanded variants: original + context phrase + domain-specific
                    query_variants = [
                        query,
                        f'"{query}"',
                        f"{query} {plan.topic}",
                    ]
                    for q in query_variants:
                        try:
                            results = await asyncio.to_thread(search_duckduckgo, q, 5)
                            for r in results:
                                url = self.normalize_url(r["url"])
                                if url not in self.seen_urls:
                                    web_url_jobs.append((r, sub.title, q))
                        except Exception as exc:
                            logger.warning(f"[Search] DDG failed for '{q}': {exc}")

                # Academic search jobs
                if use_academic:
                    academic_jobs.append((query, sub.title))

                # Wikipedia for general context
                if not use_academic:
                    wiki_jobs.append((query.split()[0] if query else "", sub.title, query))

        await _notify(
            f"🔍 Searching: {len(web_url_jobs)} web URLs + "
            f"{len(academic_jobs)} academic queries..."
        )

        # ── 1. Fetch academic sources (no scraping needed) ────────────────
        for query, subtopic in academic_jobs:
            try:
                academic_results = await academic_search(query, max_results=4)
                for r in academic_results:
                    src = self._make_academic_source(r, subtopic, query)
                    if src:
                        sources.append(src)
                await asyncio.sleep(0.5)  # polite pause for S2 API
            except Exception as exc:
                logger.warning(f"[Search] Academic search failed for '{query}': {exc}")

        # ── 2. Fetch Wikipedia context ────────────────────────────────────
        for first_word, subtopic, query in wiki_jobs[:3]:  # cap wiki calls
            try:
                wiki_results = await asyncio.to_thread(search_wikipedia, first_word or query)
                for r in wiki_results:
                    src = self._make_academic_source(r, subtopic, query)
                    if src:
                        sources.append(src)
            except Exception as exc:
                logger.debug(f"[Search] Wikipedia failed: {exc}")

        # ── 3. Scrape web URLs ────────────────────────────────────────────
        async with httpx.AsyncClient(timeout=20) as client:
            tasks = [
                self.process_url(client, r[0], r[1], r[2])
                for r in web_url_jobs
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                logger.debug(f"[Search] Fetch task error: {r}")
                continue
            if r:
                sources.append(r)

        total = len(sources)
        await _notify(f"✅ Search complete — {total} raw sources collected")
        logger.info(f"[SearchAgent] Total raw sources: {total}")
        return sources[: self.MAX_RAW_SOURCES]


search_agent = SearchAgent()
