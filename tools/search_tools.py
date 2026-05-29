"""
tools/search_tools.py

Search tools:
  search_duckduckgo()          — unchanged, your original function
  search_arxiv()               — academic papers (free, no key)
  search_semantic_scholar()    — academic abstracts (free, no key)
  search_wikipedia()           — reference context (free, no key)
  academic_search()            — arXiv + S2 combined
"""
from __future__ import annotations

import asyncio
import time
from typing import List

import httpx
from loguru import logger

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

try:
    import arxiv as arxiv_lib
    ARXIV_AVAILABLE = True
except ImportError:
    ARXIV_AVAILABLE = False

try:
    import wikipediaapi
    WIKI_AVAILABLE = True
except ImportError:
    WIKI_AVAILABLE = False


# ── Rate limiting ──────────────────────────────────────────────────────────────

_last_ddg_call: float = 0.0
MIN_INTERVAL: float = 1.2

BAD_DOMAINS = [
    "zhihu", "statista", "reddit", "quora", "pinterest",
    "facebook", "instagram", "twitter", "login", "signup", "forum",
]


def normalize_url(url: str) -> str:
    url = url.split("#")[0]
    return url.rstrip("/")


def is_good_url(url: str) -> bool:
    url = url.lower()
    return not any(bad in url for bad in BAD_DOMAINS)


def rate_limit():
    global _last_ddg_call
    elapsed = time.time() - _last_ddg_call
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_ddg_call = time.time()


# ── DuckDuckGo (Fallback) ─────────────────────────────────────────────────────

def _search_duckduckgo_raw(query: str, max_results: int = 8) -> List[dict]:
    """Your original function — unchanged."""
    if DDGS is None:
        logger.warning("[DDG] ddgs package not installed")
        return []

    results = []
    seen: set = set()

    for attempt in range(3):
        try:
            rate_limit()
            with DDGS() as ddgs:
                data = ddgs.text(query, max_results=max_results * 2)
                for r in data:
                    url = normalize_url(r.get("href", ""))
                    if not url or not is_good_url(url) or url in seen:
                        continue
                    seen.add(url)
                    results.append({
                        "title": r.get("title", ""),
                        "url": url,
                        "snippet": r.get("body", ""),
                        "source": "ddg",
                    })
                    if len(results) >= max_results:
                        break
            return results
        except Exception as e:
            if "no results" in str(e).lower():
                logger.debug(f"[DDG] No results found for query: {query}")
                return []
            logger.debug(f"[DDG] attempt {attempt + 1} failed: {e}")
            time.sleep(2 * (attempt + 1))

    return results


# ── Tavily Search (Recommended for Agents) ────────────────────────────────────

def search_tavily(query: str, max_results: int = 5) -> List[dict]:
    from config import settings
    if not settings.TAVILY_API_KEY:
        return []
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        response = client.search(query=query, max_results=max_results, search_depth="basic")
        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "source": "tavily",
            })
        return results
    except Exception as e:
        logger.warning(f"[Tavily] Search failed: {e}")
        return []


# ── Serper.dev Google Search ──────────────────────────────────────────────────

def search_serper(query: str, max_results: int = 5) -> List[dict]:
    from config import settings
    if not settings.SERPER_API_KEY:
        return []
    try:
        import requests
        url = "https://google.serper.dev/search"
        payload = {"q": query, "num": max_results}
        headers = {
            "X-API-KEY": settings.SERPER_API_KEY,
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.warning(f"[Serper] HTTP error: {response.status_code} - {response.text}")
            return []
        data = response.json()
        results = []
        for r in data.get("organic", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("link", ""),
                "snippet": r.get("snippet", ""),
                "source": "serper",
            })
        return results
    except Exception as e:
        logger.warning(f"[Serper] Search failed: {e}")
        return []


# ── Main Web Search Entrypoint (Router) ───────────────────────────────────────

def search_duckduckgo(query: str, max_results: int = 8) -> List[dict]:
    """
    Main web search entrypoint. Automatically routes to Tavily or Serper
    if their respective API keys are configured, falling back to DuckDuckGo.
    """
    from config import settings
    if settings.TAVILY_API_KEY:
        logger.info(f"[Search] Using Tavily for: '{query}'")
        return search_tavily(query, max_results)
    elif settings.SERPER_API_KEY:
        logger.info(f"[Search] Using Serper (Google) for: '{query}'")
        return search_serper(query, max_results)
    else:
        return _search_duckduckgo_raw(query, max_results)


# ── arXiv ─────────────────────────────────────────────────────────────────────

def search_arxiv(query: str, max_results: int = 5) -> List[dict]:
    """Search arXiv for academic papers. Free, no API key."""
    if not ARXIV_AVAILABLE:
        return []

    try:
        client = arxiv_lib.Client(
            page_size=max_results,
            delay_seconds=1.0,
            num_retries=2,
        )
        search = arxiv_lib.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv_lib.SortCriterion.Relevance,
        )
        results = []
        for paper in client.results(search):
            authors = ", ".join(str(a) for a in paper.authors[:3])
            content = (
                f"Title: {paper.title}\n"
                f"Authors: {authors}\n"
                f"Published: {paper.published.strftime('%Y-%m-%d') if paper.published else 'N/A'}\n\n"
                f"Abstract:\n{paper.summary}"
            )
            results.append({
                "title": paper.title,
                "url": paper.entry_id,
                "snippet": paper.summary[:300],
                "content": content,
                "source": "arxiv",
            })
        logger.debug(f"[arXiv] '{query}' → {len(results)} papers")
        return results
    except Exception as e:
        logger.warning(f"[arXiv] search failed: {e}")
        return []


# ── Semantic Scholar ───────────────────────────────────────────────────────────

async def search_semantic_scholar_async(
    query: str, max_results: int = 5
) -> List[dict]:
    """
    Semantic Scholar free REST API — no key required.
    Returns papers with title, abstract, year, authors.
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,year,authors,externalIds,openAccessPdf,url",
    }
    headers = {"User-Agent": "AutonomousResearchAI/2.0 (research@example.com)"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 429:
                await asyncio.sleep(3)
                resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception as e:
        logger.warning(f"[S2] request failed: {e}")
        return []

    results = []
    for paper in data.get("data", []):
        abstract = paper.get("abstract") or ""
        if not abstract:
            continue
        authors = ", ".join(a.get("name", "") for a in paper.get("authors", [])[:3])
        year = paper.get("year", "N/A")
        content = (
            f"Title: {paper.get('title', '')}\n"
            f"Authors: {authors}\n"
            f"Year: {year}\n\n"
            f"Abstract:\n{abstract}"
        )
        paper_url = (
            paper.get("url")
            or f"https://semanticscholar.org/paper/{paper.get('paperId', '')}"
        )
        results.append({
            "title": paper.get("title", ""),
            "url": paper_url,
            "snippet": abstract[:300],
            "content": content,
            "source": "semantic_scholar",
        })

    logger.debug(f"[S2] '{query}' → {len(results)} papers")
    return results


def search_semantic_scholar(query: str, max_results: int = 5) -> List[dict]:
    """Synchronous wrapper for Semantic Scholar."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Can't run nested event loops — use a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    search_semantic_scholar_async(query, max_results)
                )
                return future.result(timeout=20)
        return loop.run_until_complete(
            search_semantic_scholar_async(query, max_results)
        )
    except Exception as e:
        logger.warning(f"[S2] sync wrapper failed: {e}")
        return []


# ── Wikipedia ─────────────────────────────────────────────────────────────────

def search_wikipedia(query: str) -> List[dict]:
    """Fetch Wikipedia article for context. Free, no key."""
    if not WIKI_AVAILABLE:
        return []
    try:
        wiki = wikipediaapi.Wikipedia(
            language="en",
            user_agent="AutonomousResearchAI/2.0"
        )
        page = wiki.page(query)
        if not page.exists():
            return []
        content = f"Title: {page.title}\n\nSummary:\n{page.summary[:3000]}"
        return [{
            "title": page.title,
            "url": page.fullurl,
            "snippet": page.summary[:300],
            "content": content,
            "source": "wikipedia",
        }]
    except Exception as e:
        logger.debug(f"[Wikipedia] '{query}' failed: {e}")
        return []


# ── Combined academic search ───────────────────────────────────────────────────

async def academic_search(query: str, max_results: int = 5) -> List[dict]:
    """
    Run arXiv + Semantic Scholar in parallel.
    Used for subtopics with source_type=academic.
    """
    arxiv_task = asyncio.get_event_loop().run_in_executor(
        None, search_arxiv, query, max_results
    )
    s2_task = search_semantic_scholar_async(query, max_results)

    arxiv_results, s2_results = await asyncio.gather(arxiv_task, s2_task)
    return arxiv_results + s2_results
