"""
Daily News Pipeline for TechPulse AI.

Orchestrates the full sequence:
  COLLECT → CLEAN → RANK → ANALYZE → RANK AGAIN → BUILD DIGEST → SAVE

Design goals:
  - Each stage reports counts and errors independently.
  - A single article failure never aborts the entire batch.
  - Re-running on the same India-local date does NOT create duplicate digests.
  - Persists a job execution record on every run.
  - Provides a concurrency guard via a MongoDB job-lock document.
"""

from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pytz

from app.agents.cleaning_agent import run_cleaning
from app.agents.collector_agent import run_collector
from app.agents.ranking_agent import run_ranking
from app.agents.summary_agent import run_analysis
from app.config.settings import settings
from app.database.repository import (
    get_articles_for_digest,
    get_digest,
    save_digest,
    save_job_result,
)
from app.utils.logging_config import get_logger
from app.utils.ranking_utils import select_diverse_digest_articles
from app.database.connection import get_database

logger = get_logger(__name__)

_IST = pytz.timezone(settings.TIMEZONE)
_LOCK_COLLECTION = "pipeline_locks"


# ── Date helper ───────────────────────────────────────────────────────────────

def get_india_date() -> str:
    """Return today's date as YYYY-MM-DD in the Asia/Kolkata timezone."""
    return datetime.now(_IST).strftime("%Y-%m-%d")


# ── Concurrency guard ─────────────────────────────────────────────────────────

def _acquire_lock(job_name: str) -> bool:
    """
    Try to acquire a simple MongoDB-based job lock.
    Returns True if the lock was acquired, False if another instance is running.
    """
    db = get_database()
    locks = db[_LOCK_COLLECTION]
    now = datetime.now(timezone.utc)
    try:
        locks.insert_one({"job_name": job_name, "locked_at": now})
        return True
    except Exception:
        return False  # Document already exists (unique index)


def _release_lock(job_name: str) -> None:
    db = get_database()
    db[_LOCK_COLLECTION].delete_one({"job_name": job_name})


def _ensure_lock_index() -> None:
    db = get_database()
    db[_LOCK_COLLECTION].create_index("job_name", unique=True)


# ── Digest builder ────────────────────────────────────────────────────────────

def _build_digest(date_str: str) -> Dict[str, Any]:
    """Fetch top candidates and select a diverse, non-duplicate top-N digest."""
    candidate_pool = get_articles_for_digest(limit=settings.TOP_ARTICLES_FOR_DIGEST * 3)
    articles = select_diverse_digest_articles(
        candidate_pool,
        limit=settings.TOP_ARTICLES_FOR_DIGEST,
        near_duplicate_threshold=0.50,
        max_per_category=3,
    )

    digest_articles = []
    for rank, art in enumerate(articles, start=1):
        digest_articles.append({
            "rank": rank,
            "title": art.get("clean_title") or art.get("title", ""),
            "source": art.get("source", ""),
            "category": art.get("category", ""),
            "score": art.get("score"),
            "ai_score": art.get("ai_score"),
            "sentiment": art.get("sentiment"),
            "importance": art.get("importance"),
            "summary": art.get("summary") or art.get("description") or "",
            "link": art.get("link", ""),
        })

    return {
        "date": date_str,
        "created_at": datetime.now(timezone.utc),
        "article_count": len(digest_articles),
        "articles": digest_articles,
        "whatsapp_sent": False,
        "whatsapp_sent_at": None,
    }


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_daily_pipeline(force: bool = False) -> Dict[str, Any]:
    """
    Execute the full daily news pipeline.

    Parameters
    ----------
    force : bool
        If True, regenerates the digest even if one already exists for today.

    Returns
    -------
    dict : combined result from all pipeline stages plus job metadata.
    """
    _ensure_lock_index()

    job_name = "daily_pipeline"
    started_at = datetime.now(timezone.utc)
    date_str = get_india_date()

    result: Dict[str, Any] = {
        "job_name": job_name,
        "started_at": started_at,
        "finished_at": None,
        "success": False,
        "date": date_str,
        "collected": 0,
        "cleaned": 0,
        "ranked": 0,
        "analyzed": 0,
        "digest_date": None,
        "errors": [],
    }

    # ── Concurrency guard ─────────────────────────────────────────────────────
    if not _acquire_lock(job_name):
        msg = f"Pipeline lock held — another instance of '{job_name}' is running. Aborting."
        logger.warning(msg)
        result["errors"].append(msg)
        _persist_result(result)
        return result

    logger.info("=== Daily Pipeline started for %s ===", date_str)

    try:
        # ── Stage 1: Collect ──────────────────────────────────────────────────
        logger.info("Stage 1/5: Collect")
        try:
            collect_stats = run_collector()
            result["collected"] = collect_stats.get("articles_saved", 0)
            for err in collect_stats.get("errors", []):
                result["errors"].append(f"[collect] {err['feed']}: {err['error']}")
        except Exception as exc:
            logger.error("Collect stage failed: %s", exc)
            result["errors"].append(f"[collect] {type(exc).__name__}: {exc}")

        # ── Stage 2: Clean ────────────────────────────────────────────────────
        logger.info("Stage 2/5: Clean")
        try:
            clean_stats = run_cleaning()
            result["cleaned"] = clean_stats.get("cleaned", 0)
        except Exception as exc:
            logger.error("Clean stage failed: %s", exc)
            result["errors"].append(f"[clean] {type(exc).__name__}: {exc}")

        # ── Stage 3: Initial rank (before AI analysis) ────────────────────────
        logger.info("Stage 3/5: Rank")
        try:
            rank_stats = run_ranking()
            result["ranked"] = rank_stats.get("ranked", 0)
        except Exception as exc:
            logger.error("Rank stage failed: %s", exc)
            result["errors"].append(f"[rank] {type(exc).__name__}: {exc}")

        # ── Stage 4: AI Analysis ──────────────────────────────────────────────
        logger.info("Stage 4/5: Analyze")
        try:
            analysis_stats = run_analysis()
            result["analyzed"] = analysis_stats.get("analyzed", 0)
        except Exception as exc:
            logger.error("Analysis stage failed: %s", exc)
            result["errors"].append(f"[analyze] {type(exc).__name__}: {exc}")

        # ── Stage 4b: Re-rank after AI analysis (ai_score now populated) ──────
        logger.info("Stage 4b/5: Re-rank after AI analysis")
        try:
            run_ranking()
        except Exception as exc:
            logger.warning("Re-rank stage failed (non-fatal): %s", exc)

        # ── Stage 5: Build and save digest ────────────────────────────────────
        logger.info("Stage 5/5: Build digest")
        existing = get_digest(date_str)
        if existing and not force:
            logger.info("Digest for %s already exists — skipping rebuild", date_str)
            result["digest_date"] = date_str
        else:
            try:
                digest = _build_digest(date_str)
                if save_digest(digest):
                    result["digest_date"] = date_str
                    logger.info("Digest saved: %d articles", digest["article_count"])
                else:
                    result["errors"].append("[digest] Failed to save digest to MongoDB")
            except Exception as exc:
                logger.error("Digest build failed: %s", exc)
                result["errors"].append(f"[digest] {type(exc).__name__}: {exc}")

        result["success"] = result["digest_date"] is not None

    except Exception as exc:
        logger.error("Unexpected pipeline failure: %s\n%s", exc, traceback.format_exc())
        result["errors"].append(f"[pipeline] {type(exc).__name__}: {exc}")

    finally:
        _release_lock(job_name)
        result["finished_at"] = datetime.now(timezone.utc)
        duration = (result["finished_at"] - started_at).total_seconds()
        result["duration_seconds"] = round(duration, 1)
        _persist_result(result)

    logger.info(
        "=== Daily Pipeline finished in %.1fs — success=%s ===",
        result["duration_seconds"],
        result["success"],
    )
    return result


def _persist_result(result: Dict[str, Any]) -> None:
    """Save job result to history. Failure here is non-fatal."""
    try:
        save_job_result(result)
    except Exception as exc:
        logger.error("Failed to persist job result: %s", exc)
