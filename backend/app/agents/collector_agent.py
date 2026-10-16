"""
News Collector Agent for TechPulse AI.

Fetches articles from configured RSS feeds concurrently using bounded thread workers.
Normalises articles, strips tracking parameters, and persists new articles to MongoDB.
Each feed failure is isolated so one bad source never stops or delays the rest.
"""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List

import feedparser

from app.config.settings import settings
from app.services.news_service import process_article
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

_FEED_TIMEOUT = settings.RSS_FEED_TIMEOUT_SECONDS
_MAX_WORKERS = 5  # Bounded concurrency to respect upstream rate limits


def _process_single_feed(feed_cfg: Dict[str, str]) -> Dict[str, Any]:
    """Fetch and process articles for a single RSS feed."""
    name = feed_cfg["name"]
    url = feed_cfg["url"]
    category = feed_cfg["category"]

    feed_stat: Dict[str, Any] = {
        "name": name,
        "succeeded": False,
        "articles_found": 0,
        "articles_saved": 0,
        "error": None,
    }

    try:
        parsed = feedparser.parse(url)

        if parsed.bozo:
            logger.warning(
                "Feed %s returned bozo error: %s",
                name,
                getattr(parsed, "bozo_exception", "unknown"),
            )

        entries = parsed.entries[: settings.MAX_ARTICLES_PER_FEED]
        feed_stat["articles_found"] = len(entries)

        saved = 0
        for entry in entries:
            try:
                if process_article(entry, name, category):
                    saved += 1
            except Exception as entry_exc:
                logger.debug(
                    "Skipped entry in %s: %s",
                    name,
                    type(entry_exc).__name__,
                )

        feed_stat["articles_saved"] = saved
        feed_stat["succeeded"] = True
        logger.info("Feed %s: saved %d / %d articles", name, saved, len(entries))

    except Exception as feed_exc:
        error_msg = f"{type(feed_exc).__name__}: {feed_exc}"
        feed_stat["error"] = error_msg
        logger.error("Feed %s failed: %s", name, error_msg)

    return feed_stat


def run_collector() -> Dict[str, Any]:
    """
    Collect news from all RSS feeds concurrently with bounded concurrency.

    Returns a statistics dict:
        {
            "feeds_attempted": int,
            "feeds_succeeded": int,
            "feeds_failed": int,
            "articles_found": int,
            "articles_saved": int,
            "errors": [ {"feed": str, "error": str}, ... ]
        }
    """
    logger.info("=== Collector Agent started (concurrent pool) ===")

    stats: Dict[str, Any] = {
        "feeds_attempted": 0,
        "feeds_succeeded": 0,
        "feeds_failed": 0,
        "articles_found": 0,
        "articles_saved": 0,
        "errors": [],
    }

    feeds = settings.RSS_FEEDS
    stats["feeds_attempted"] = len(feeds)

    original_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(_FEED_TIMEOUT)

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            future_to_feed = {
                executor.submit(_process_single_feed, f): f["name"]
                for f in feeds
            }

            for future in as_completed(future_to_feed):
                feed_name = future_to_feed[future]
                try:
                    feed_stat = future.result()
                    stats["articles_found"] += feed_stat["articles_found"]
                    stats["articles_saved"] += feed_stat["articles_saved"]

                    if feed_stat["succeeded"]:
                        stats["feeds_succeeded"] += 1
                    else:
                        stats["feeds_failed"] += 1
                        stats["errors"].append({
                            "feed": feed_name,
                            "error": feed_stat["error"] or "Unknown error",
                        })
                except Exception as exc:
                    stats["feeds_failed"] += 1
                    error_msg = f"{type(exc).__name__}: {exc}"
                    stats["errors"].append({"feed": feed_name, "error": error_msg})
                    logger.error("Feed %s task crashed: %s", feed_name, error_msg)

    finally:
        socket.setdefaulttimeout(original_timeout)

    logger.info(
        "=== Collector done: %d/%d feeds ok, %d new articles saved ===",
        stats["feeds_succeeded"],
        stats["feeds_attempted"],
        stats["articles_saved"],
    )
    return stats
