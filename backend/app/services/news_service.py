"""
News service: normalise a raw feedparser entry and persist it.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.database.repository import upsert_article
from app.utils.logging_config import get_logger
from app.utils.text_utils import clean_title, normalize_url, parse_published_date

logger = get_logger(__name__)


def process_article(
    entry: Any,
    source: str,
    category: str,
) -> bool:
    """
    Normalise a feedparser entry and store it in MongoDB.
    Returns True when a new article was saved, False if it was a duplicate
    or if required fields were missing.
    """
    # ── Required fields ───────────────────────────────────────────────────────
    title: str = getattr(entry, "title", "").strip()
    link: str = getattr(entry, "link", "").strip()

    if not title or not link:
        logger.debug("Skipped entry — missing title or link from %s", source)
        return False

    # Ignore links that are not real URLs
    if not link.startswith("http"):
        logger.debug("Skipped non-http link: %s", link[:80])
        return False

    # ── Optional fields ───────────────────────────────────────────────────────
    published_raw: str = getattr(entry, "published", "") or ""
    published_dt: Optional[datetime] = parse_published_date(published_raw)

    description: str = ""
    if hasattr(entry, "summary"):
        # Strip HTML tags from feed summaries
        description = re.sub(r"<[^>]+>", "", entry.summary).strip()
        description = description[:500]  # cap at 500 chars

    image: str = ""
    if hasattr(entry, "media_content") and entry.media_content:
        image = entry.media_content[0].get("url", "")
    elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        image = entry.media_thumbnail[0].get("url", "")

    now = datetime.now(timezone.utc)
    canonical = normalize_url(link)

    document: Dict[str, Any] = {
        "title": title,
        "clean_title": clean_title(title, strip_publisher_suffix=True),
        "link": link,
        "canonical_link": canonical,
        "published": published_raw,
        "published_dt": published_dt,
        "description": description,
        "image": image,
        "source": source,
        "category": category,
        "created_at": now,
        "status": "raw",
    }

    saved = upsert_article(document)
    if saved:
        logger.debug("Saved: %s", title[:70])
    return saved
