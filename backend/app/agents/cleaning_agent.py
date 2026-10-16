"""
Cleaning and Deduplication Agent for TechPulse AI.

Processes raw articles: normalises titles, validates fields,
parses publication dates, and marks duplicates. Idempotent —
safe to run multiple times on the same data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from pymongo.errors import PyMongoError

from app.database.connection import get_database
from app.config.settings import settings
from app.utils.logging_config import get_logger
from app.utils.text_utils import clean_title, parse_published_date, strip_html, truncate_text

logger = get_logger(__name__)


def run_cleaning() -> Dict[str, Any]:
    """
    Clean all articles that are still in 'raw' status.

    Returns a statistics dict:
        {
            "processed": int,
            "cleaned": int,
            "skipped_invalid": int,
            "errors": int
        }
    """
    logger.info("=== Cleaning Agent started ===")

    stats: Dict[str, Any] = {
        "processed": 0,
        "cleaned": 0,
        "skipped_invalid": 0,
        "errors": 0,
    }

    db = get_database()
    collection = db[settings.ARTICLES_COLLECTION]

    # Only process articles that haven't been cleaned yet
    cursor = collection.find({"status": "raw"})

    for article in cursor:
        stats["processed"] += 1
        article_id = article["_id"]

        try:
            updates = _clean_article(article)

            if updates is None:
                # Article failed validation — mark as invalid
                collection.update_one(
                    {"_id": article_id},
                    {"$set": {"status": "invalid", "cleaned_at": datetime.now(timezone.utc)}},
                )
                stats["skipped_invalid"] += 1
                continue

            updates["status"] = "cleaned"
            updates["cleaned_at"] = datetime.now(timezone.utc)

            collection.update_one({"_id": article_id}, {"$set": updates})
            stats["cleaned"] += 1

        except PyMongoError as exc:
            logger.error("DB error cleaning article %s: %s", article_id, exc)
            stats["errors"] += 1
        except Exception as exc:
            logger.error("Unexpected error cleaning article %s: %s", article_id, type(exc).__name__)
            stats["errors"] += 1

    logger.info(
        "=== Cleaning done: %d cleaned, %d invalid, %d errors ===",
        stats["cleaned"],
        stats["skipped_invalid"],
        stats["errors"],
    )
    return stats


def _clean_article(article: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Validate and clean a single article document.
    Returns a dict of fields to set, or None if the article is invalid.
    """
    title = (article.get("title") or "").strip()
    link = (article.get("link") or "").strip()

    # Hard requirements: title and link must be present and valid
    if not title or len(title) < 5:
        logger.debug("Invalid title for link: %s", link[:80])
        return None

    if not link or not link.startswith("http"):
        logger.debug("Invalid link: %s", link[:80])
        return None

    updates: Dict[str, Any] = {}

    # Normalise title
    updates["clean_title"] = clean_title(title)

    # Normalise description / strip HTML
    raw_desc = article.get("description") or ""
    updates["description"] = truncate_text(strip_html(raw_desc), 500)

    # Normalise publication date
    raw_published = article.get("published") or ""
    if not article.get("published_dt"):
        parsed_dt = parse_published_date(raw_published)
        if parsed_dt:
            updates["published_dt"] = parsed_dt

    # Fallback: if no publication date at all, use created_at
    if not article.get("published_dt") and not updates.get("published_dt"):
        updates["published_dt"] = article.get("created_at", datetime.now(timezone.utc))

    return updates
