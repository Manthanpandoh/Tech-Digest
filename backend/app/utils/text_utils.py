"""
Text and URL processing utilities for TechPulse AI.
Includes URL normalization, title cleaning, HTML stripping, date parsing,
and near-duplicate detection helpers.
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional, Set
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Common URL tracking query parameters to remove
_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gclsrc", "msclkid", "dclid",
    "ref", "ref_src", "ref_url", "ocid", "ncid",
    "mc_cid", "mc_eid", "_ga", "_gl", "_hsenc", "_hsmi",
    "cmpid", "feedname", "feedType", "rss",
})

# Common publisher suffix patterns in RSS headlines (e.g., "Headline - TechCrunch")
_PUBLISHER_SUFFIX_RE = re.compile(
    r"\s+[-–—|]\s+(?:TechCrunch|The Verge|Wired|Ars Technica|MIT Technology Review|"
    r"Reuters|Bloomberg|CNBC|The Information|Engadget|VentureBeat|ZDNET|"
    r"Google News|Google AI Blog|Hacker News|BBC News|The New York Times)$",
    re.IGNORECASE,
)


def normalize_url(url: str) -> str:
    """
    Normalize an article URL by stripping marketing tracking parameters,
    normalizing scheme/domain to lowercase, removing trailing slashes,
    and dropping unnecessary URL fragments.
    Preserves non-tracking query parameters required for page routing.
    """
    if not url or not isinstance(url, str):
        return ""

    url = url.strip()
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return url

        # Lowercase scheme and domain
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Clean query parameters
        filtered_query = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key.lower() not in _TRACKING_PARAMS:
                filtered_query.append((key, value))

        # Sort query params for consistent canonical representation
        new_query = urlencode(filtered_query)

        # Normalize path: remove redundant trailing slash unless it's root
        path = parsed.path
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        # Omit URL fragment (#anchor) for canonical deduplication
        canonical = urlunparse((scheme, netloc, path, parsed.params, new_query, ""))
        return canonical
    except Exception:
        return url


def clean_title(title: str, strip_publisher_suffix: bool = False) -> str:
    """
    Normalize whitespace, decode HTML entities, and strip leading/trailing spaces.
    Optionally strips trailing publisher suffixes (e.g. ' - TechCrunch').
    """
    if not title or not isinstance(title, str):
        return ""

    # Decode HTML entities (e.g., &amp; -> &, &#8217; -> ')
    text = html.unescape(title)

    # Normalize smart quotes to standard ASCII
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\n", " ").replace("\r", " ").strip()

    if strip_publisher_suffix:
        text = _PUBLISHER_SUFFIX_RE.sub("", text).strip()

    return text


def parse_published_date(raw: str) -> Optional[datetime]:
    """
    Parse a publication date string to a timezone-aware UTC datetime.
    Accepts RFC 2822 (standard RSS/Atom) and ISO 8601 variants.
    Returns None if parsing fails.
    """
    if not raw or not isinstance(raw, str) or not raw.strip():
        return None

    # Try RFC 2822 first (standard RSS/Atom format)
    try:
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Try ISO 8601 variants
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue

    return None


def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text to max_length characters, appending '…' if cut."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "…"


def strip_html(text: str) -> str:
    """Remove all HTML tags and decode remaining HTML entities from a string."""
    if not text:
        return ""
    stripped = re.sub(r"<[^>]+>", "", text).strip()
    return html.unescape(stripped)


def tokenize_title(title: str) -> Set[str]:
    """
    Extract meaningful normalized word tokens for title similarity comparison.
    Filters stop words, punctuation, and common headline action verbs.
    """
    cleaned = clean_title(title, strip_publisher_suffix=True).lower()
    words = re.findall(r"[a-z0-9]{3,}", cleaned)
    # Common English stop words and generic headline verbs
    stop_words = {
        "the", "and", "for", "with", "that", "this", "from", "are",
        "was", "were", "will", "has", "have", "had", "its", "about",
        "into", "after", "over", "more", "says", "said", "new", "how",
        "launches", "unveils", "announces", "releases", "introduces",
        "reveals", "debuts", "rolls", "expands", "updates", "features",
    }
    return {w for w in words if w not in stop_words}


def title_similarity(title1: str, title2: str) -> float:
    """
    Compute hybrid Jaccard & Szymkiewicz-Simpson Overlap similarity (0.0 to 1.0)
    between two titles. Accurately detects syndicated, concise, or rephrased versions
    of the same underlying news story.
    """
    tokens1 = tokenize_title(title1)
    tokens2 = tokenize_title(title2)

    if not tokens1 or not tokens2:
        return 0.0

    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    min_len = min(len(tokens1), len(tokens2))

    jaccard = intersection / union if union > 0 else 0.0
    overlap = intersection / min_len if min_len > 0 else 0.0

    # When headlines share 3 or more distinctive content words, prioritize containment overlap
    if intersection >= 3:
        score = max(jaccard, overlap)
    else:
        score = (0.4 * jaccard) + (0.6 * overlap)
    return round(score, 4)


def compute_content_hash(title: str, content: str) -> str:
    """
    Generate a stable SHA-256 hash of an article's title + content
    for caching AI analysis results and avoiding duplicate LLM calls.
    """
    norm = f"{clean_title(title).lower()}|{truncate_text(strip_html(content), 1000).lower()}"
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
