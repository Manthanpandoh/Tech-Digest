"""
Ranking and recommendation engine for TechPulse AI.

Transparent multi-factor ranking strategy incorporating:
  1. Publication freshness via continuous exponential half-life decay.
  2. Source authority & journalistic editorial quality tiers.
  3. LLM semantic analysis (relevance score + editorial importance).
  4. High-signal domain keyword matching.
  5. Story diversity and near-duplicate suppression for daily digest curation.

Score Range: 0.0 – 100.0 (calibrated and bounded).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.utils.text_utils import title_similarity

# High-signal technology keywords and domain weights
_KEYWORD_WEIGHTS: Dict[str, float] = {
    # Frontier AI & models (high signal)
    "openai": 4.0, "chatgpt": 4.0, "gpt-4": 4.0, "gpt-5": 4.0, "llm": 3.5,
    "gemini": 3.5, "claude": 3.5, "deepseek": 3.5, "anthropic": 3.5,
    "artificial intelligence": 3.0, "machine learning": 3.0, "deep learning": 3.0,
    # Infrastructure & hardware
    "nvidia": 4.0, "semiconductor": 3.5, "gpu": 3.0, "tsmc": 3.0, "quantum": 3.5,
    # Big tech announcements
    "google": 2.5, "microsoft": 2.5, "apple": 2.5, "meta": 2.5, "amazon": 2.5,
    # Security & critical infra
    "cybersecurity": 3.5, "zero-day": 4.0, "data breach": 3.5, "ransomware": 3.5,
    "vulnerability": 3.0,
    # Cloud & systems
    "cloud": 2.5, "aws": 2.5, "azure": 2.5, "kubernetes": 3.0,
    # Business impact
    "acquisition": 3.0, "ipo": 3.0, "funding": 2.5, "billion": 2.5,
}

_MAX_KEYWORD_SCORE = 20.0

# Editorial source reputation tiers
_SOURCE_TIERS: Dict[str, float] = {
    # Tier 1: In-depth primary technical journalism & research (+10 pts)
    "mit technology review": 10.0,
    "ars technica": 10.0,
    "wired": 10.0,
    "wired technology": 10.0,
    "google ai blog": 10.0,
    "techcrunch": 9.0,
    # Tier 2: Established tech media (+5 pts)
    "the verge": 6.0,
    "google machine learning": 6.0,
    "google cloud computing": 5.0,
    "google cybersecurity": 5.0,
    "google data science": 5.0,
}


def _calculate_recency_score(pub_dt: Optional[datetime]) -> float:
    """
    Calculate recency score using an exponential half-life decay function:
        score = 35 * 2^(-age_hours / 24)
    - 0 hours old: 35.0 pts
    - 6 hours old: 29.4 pts
    - 12 hours old: 24.7 pts
    - 24 hours old: 17.5 pts
    - 48 hours old: 8.75 pts
    - 7 days old: ~2.0 pts
    Minimum score: 2.0 (if date exists). Unknown date: 5.0 pts.
    """
    if not pub_dt:
        return 5.0

    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)

    now_utc = datetime.now(timezone.utc)
    age_hours = max(0.0, (now_utc - pub_dt).total_seconds() / 3600.0)

    # 24-hour half-life exponential decay
    decay = math.pow(2.0, -age_hours / 24.0)
    score = 35.0 * decay
    return max(2.0, min(35.0, score))


def _calculate_source_score(source_name: Optional[str]) -> float:
    """Assign source tier bonus based on editorial track record."""
    if not source_name:
        return 0.0
    cleaned = source_name.lower().strip()
    return _SOURCE_TIERS.get(cleaned, 2.0)


def _calculate_keyword_score(title: str, description: str) -> float:
    """Score high-signal technical keywords in title and description."""
    combined = f"{title.lower()} {description.lower()}"
    total = 0.0
    matched_keywords = set()

    for kw, weight in _KEYWORD_WEIGHTS.items():
        if kw in combined and kw not in matched_keywords:
            matched_keywords.add(kw)
            # Give 1.5x bonus if keyword appears in the title
            multiplier = 1.5 if kw in title.lower() else 1.0
            total += weight * multiplier
            if total >= _MAX_KEYWORD_SCORE:
                return _MAX_KEYWORD_SCORE

    return round(min(_MAX_KEYWORD_SCORE, total), 2)


def _calculate_ai_score_component(
    ai_score: Optional[int | float],
    importance: Optional[str] = None,
) -> float:
    """
    Calculate AI contribution (0–35 pts):
      - Base AI score (0–100 scaled to 0–25 pts)
      - Importance bonus (High: +10, Medium: +5, Low: +0)
    Capped at 35 pts max.
    """
    if ai_score is None:
        return 0.0

    try:
        val = float(ai_score)
        val = max(0.0, min(100.0, val))
    except (ValueError, TypeError):
        return 0.0

    base_pts = (val / 100.0) * 25.0

    importance_bonus = 0.0
    if importance:
        imp_lower = importance.lower()
        if imp_lower == "high":
            importance_bonus = 10.0
        elif imp_lower == "medium":
            importance_bonus = 5.0

    return min(35.0, base_pts + importance_bonus)


def calculate_score(article: Dict[str, Any]) -> float:
    """
    Calculate a composite ranking score for a single article.

    Score Breakdown:
      - Recency: 0–35 pts (exponential half-life decay)
      - AI Evaluation: 0–35 pts (ai_score + editorial importance)
      - Domain Keywords: 0–20 pts (high-signal tech topics)
      - Source Quality: 0–10 pts (journalistic tier)
    Total: 0.0 to 100.0
    """
    title = (article.get("clean_title") or article.get("title") or "").strip()
    description = (article.get("description") or "").strip()
    source = article.get("source") or ""
    pub_dt = article.get("published_dt") or article.get("created_at")
    ai_score = article.get("ai_score")
    importance = article.get("importance")

    recency_pts = _calculate_recency_score(pub_dt)
    source_pts = _calculate_source_score(source)
    keyword_pts = _calculate_keyword_score(title, description)
    ai_pts = _calculate_ai_score_component(ai_score, importance)

    total = recency_pts + source_pts + keyword_pts + ai_pts
    return round(max(0.0, min(100.0, total)), 2)


def select_diverse_digest_articles(
    articles: List[Dict[str, Any]],
    limit: int = 10,
    near_duplicate_threshold: float = 0.40,
    max_per_category: int = 3,
) -> List[Dict[str, Any]]:
    """
    Select the top-N articles for the daily digest ensuring:
      1. Story Diversity: Articles describing the exact same event/story
         (title Jaccard similarity >= near_duplicate_threshold) are filtered out.
      2. Category Balance: No single category dominates the top-N digest
         (at most max_per_category articles, relaxed if candidate pool is small).
      3. Global Quality: Candidate articles are ranked by composite score.
    """
    if not articles:
        return []

    # Sort descending by composite score
    sorted_candidates = sorted(
        articles,
        key=lambda a: (a.get("score") or 0.0),
        reverse=True,
    )

    selected: List[Dict[str, Any]] = []
    category_counts: Dict[str, int] = {}

    # First pass: enforce strict diversity and category limits
    for cand in sorted_candidates:
        if len(selected) >= limit:
            break

        cand_title = cand.get("clean_title") or cand.get("title") or ""
        cand_cat = cand.get("category") or cand.get("ai_category") or "Other"

        # Check for near-duplicate against already selected stories
        is_duplicate = False
        for sel in selected:
            sel_title = sel.get("clean_title") or sel.get("title") or ""
            sim = title_similarity(cand_title, sel_title)
            if sim >= near_duplicate_threshold:
                is_duplicate = True
                break

        if is_duplicate:
            continue

        # Check category capacity
        current_cat_count = category_counts.get(cand_cat, 0)
        if current_cat_count >= max_per_category:
            continue

        selected.append(cand)
        category_counts[cand_cat] = current_cat_count + 1

    # Second pass: if under limit, fill remaining slots from distinct stories
    if len(selected) < limit:
        for cand in sorted_candidates:
            if len(selected) >= limit:
                break
            if cand in selected:
                continue

            cand_title = cand.get("clean_title") or cand.get("title") or ""
            is_duplicate = False
            for sel in selected:
                sel_title = sel.get("clean_title") or sel.get("title") or ""
                if title_similarity(cand_title, sel_title) >= near_duplicate_threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                selected.append(cand)

    return selected
