"""
tools/normalizer.py

Cleans raw scraped text before extraction.
Key fix vs original: remove_unicode_noise() no longer strips Greek letters,
math symbols, or other valid scientific characters (α, β, μ, %, ≥, ≤, etc.)
"""
import re

MIN_CONTENT_LENGTH = 500

# Scientific characters to KEEP (was stripped in original)
# Greek letters, arrows, math operators, degree symbols, etc.
_KEEP_UNICODE = re.compile(
    r"[^\x00-\x7F"                     # all ASCII
    r"\u00B0-\u00B9"                    # ° superscripts
    r"\u00C0-\u024F"                    # Latin extended
    r"\u0391-\u03C9"                    # Greek α-ω
    r"\u2019\u2018\u201C\u201D"         # smart quotes
    r"\u2013\u2014"                     # em/en dash
    r"\u00B5\u03BC"                     # mu / micro sign
    r"\u2264\u2265\u2260\u00B1"         # ≤ ≥ ≠ ±
    r"\u00D7\u00F7"                     # × ÷
    r"\u2192\u2190\u2194"               # arrows
    r"]+"
)


def remove_citations(text: str) -> str:
    text = re.sub(r'\[\d+\]', ' ', text)
    text = re.sub(r'\(\d{4}\)', ' ', text)
    return text


def remove_reference_sections(text: str) -> str:
    patterns = [
        r'References\s*\n.*',
        r'Bibliography\s*\n.*',
        r'See also\s*\n.*',
        r'Footnotes\s*\n.*',
        r'External links\s*\n.*',
        r'Further reading\s*\n.*',
    ]
    for p in patterns:
        text = re.sub(p, ' ', text, flags=re.S | re.I)
    return text


def remove_identifiers(text: str) -> str:
    text = re.sub(r'doi:\s*\S+', ' ', text, flags=re.I)
    text = re.sub(r'ISBN[\s-]*[\dX\-]+', ' ', text, flags=re.I)
    text = re.sub(r'ISSN[\s-]*[\d\-X]+', ' ', text, flags=re.I)
    text = re.sub(r'arXiv:\s*\S+', ' ', text, flags=re.I)
    return text


def remove_urls(text: str) -> str:
    return re.sub(r'https?://\S+', ' ', text)


def remove_unicode_noise(text: str) -> str:
    """
    Remove non-printable and truly garbage Unicode while keeping:
    - Greek letters (α β γ etc.) — common in scientific papers
    - Math symbols (≤ ≥ ± × etc.)
    - Latin extended characters
    - Smart quotes and dashes
    """
    return _KEEP_UNICODE.sub(' ', text)


def normalize_whitespace(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def remove_short_lines(text: str) -> str:
    lines = text.split(".")
    good = [line for line in lines if len(line.strip()) > 40]
    return ". ".join(good)


def normalize_content(text: str) -> str | None:
    text = remove_citations(text)
    text = remove_reference_sections(text)
    text = remove_identifiers(text)
    text = remove_urls(text)
    text = remove_unicode_noise(text)
    text = remove_short_lines(text)
    text = normalize_whitespace(text)

    if len(text) < MIN_CONTENT_LENGTH:
        return None

    return text
