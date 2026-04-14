"""
tools/scraper.py

Your original scraper — fully preserved.
One addition: `readability-lxml` added as the second-tier extractor
(between trafilatura and the BS4 fallback). This was present in your
architecture diagram but missing from the code.
"""
import asyncio
import hashlib
import re
import time
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

try:
    import trafilatura
except Exception:
    trafilatura = None

try:
    from readability import Document as ReadabilityDocument
except Exception:
    ReadabilityDocument = None

from tools.normalizer import normalize_content


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html",
    "Accept-Language": "en-US,en;q=0.9",
}

BAD_DOMAINS = [
    "pinterest", "facebook", "instagram", "twitter", "linkedin",
    "reddit", "quora", "login", "signup", "accounts.google",
]

BAD_EXTENSIONS = [".pdf", ".jpg", ".png", ".jpeg", ".zip", ".mp4"]

BAD_PATTERNS = [
    "enable javascript", "cookie policy", "accept cookies",
    "sign up", "log in", "404 error", "page not found",
]

MIN_CONTENT = 500
MAX_CONTENT = 300_000

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about",
    "your", "you", "are", "was", "were", "been", "will", "would", "shall",
    "have", "has", "had", "not", "but", "can", "could", "may", "might",
    "what", "which", "when", "where", "why", "how", "who", "whom", "whose",
    "impact", "analysis", "research", "study", "report", "overview",
    "article", "blog", "guide", "intro", "introduction", "latest", "new",
}


def extract_domain(url):
    try:
        return urlparse(url).netloc
    except Exception:
        return "unknown"


def is_bad_url(url):
    url = url.lower()
    if any(url.endswith(ext) for ext in BAD_EXTENSIONS):
        return True
    if "youtube" in url:
        return True
    return any(bad in url for bad in BAD_DOMAINS)


def clean_text(text):
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\x00-\x7F]+", " ", text)
    return text.strip()


def tokenize(text):
    return [
        token for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


def extract_trafilatura(html, url):
    try:
        if trafilatura is None:
            return None
        return trafilatura.extract(html, url=url, include_tables=False, include_comments=False)
    except Exception:
        return None


def extract_readability(html):
    """
    Second-tier extractor using readability-lxml.
    Better than BS4 for news articles and blog posts.
    """
    try:
        if ReadabilityDocument is None:
            return ""
        doc = ReadabilityDocument(html)
        content_html = doc.summary()
        soup = BeautifulSoup(content_html, "html.parser")
        return soup.get_text(" ")
    except Exception:
        return ""


def fallback_extract(html):
    """Third-tier: raw BS4 extraction."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "button"]):
        tag.decompose()
    return soup.get_text(" ")


def garbage_score(text):
    text = text.lower()
    return sum(1 for bad in BAD_PATTERNS if bad in text)


def domain_score(url):
    url = url.lower()
    if ".edu" in url:
        return 0.95
    if ".gov" in url:
        return 0.95
    if "arxiv" in url:
        return 0.90
    if "nature" in url:
        return 0.95
    if "sciencedirect" in url:
        return 0.90
    if "mit.edu" in url:
        return 0.95
    if "stanford" in url:
        return 0.95
    if "reuters" in url:
        return 0.85
    if "bbc" in url:
        return 0.85
    if "wikipedia" in url:
        return 0.70
    return 0.60


def query_score(content, query):
    if not content or not query:
        return 0
    query_terms = tokenize(query)
    if not query_terms:
        return 0
    content_lower = content.lower()
    content_terms = set(re.findall(r"[a-z0-9]+", content_lower))
    unique_query_terms = list(dict.fromkeys(query_terms))
    coverage = len(set(unique_query_terms) & content_terms) / max(len(set(unique_query_terms)), 1)
    capped_hits = sum(min(content_lower.count(term), 3) for term in set(unique_query_terms))
    density = capped_hits / max(len(set(unique_query_terms)) * 3, 1)
    phrase_bonus = 0.15 if query.lower().strip() in content_lower else 0.0
    score = min((0.7 * coverage) + (0.3 * density) + phrase_bonus, 1.0)
    return int(round(score * 100))


def content_hash(text):
    return hashlib.md5(text[:4000].encode()).hexdigest()


async def fetch_page(client, url, retries=2):
    if is_bad_url(url):
        return None

    for attempt in range(retries):
        try:
            start = time.time()
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            fetch_time = time.time() - start

            if response.status_code != 200:
                continue

            html = response.text
            if not html or len(html) > MAX_CONTENT:
                return None

            # Tier 1: trafilatura (best for articles)
            content = extract_trafilatura(html, url)

            # Tier 2: readability-lxml (good for news/blogs)
            if not content or len(content) < 400:
                content = extract_readability(html)

            # Tier 3: raw BS4
            if not content or len(content) < 400:
                content = fallback_extract(html)

            content = clean_text(content)
            content = normalize_content(content)

            if not content or len(content) < MIN_CONTENT:
                return None

            if garbage_score(content) > 3:
                return None

            return content[:15000], fetch_time

        except Exception:
            await asyncio.sleep(1)

    return None
