"""
Evaluation metrics computation for TechPulse AI.
Implements standard Information Retrieval (IR) and Classification metrics:
  - NDCG@10 (Normalized Discounted Cumulative Gain)
  - Precision@10 (Tech Relevance)
  - Near-Duplicate Collision Rate
  - Topic Diversity (Shannon Entropy & Unique Category Ratio)
  - Category Classification Accuracy and Macro F1
  - Summary Grounding & Entity Consistency Rate
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Sequence, Set


def compute_dcg(relevance_scores: Sequence[float], k: int = 10) -> float:
    """Calculate Discounted Cumulative Gain up to rank k."""
    dcg = 0.0
    for idx, rel in enumerate(relevance_scores[:k], start=1):
        # 2^rel - 1 / log2(idx + 1)
        dcg += (math.pow(2.0, rel) - 1.0) / math.log2(idx + 1.0)
    return dcg


def compute_ndcg_at_k(
    ranked_relevances: Sequence[float],
    ideal_relevances: Sequence[float],
    k: int = 10,
) -> float:
    """
    Compute Normalized Discounted Cumulative Gain at rank K.
    Returns float in range [0.0, 1.0].
    """
    if not ranked_relevances or not ideal_relevances:
        return 0.0

    actual_dcg = compute_dcg(ranked_relevances, k=k)
    ideal_dcg = compute_dcg(sorted(ideal_relevances, reverse=True), k=k)

    if ideal_dcg == 0.0:
        return 0.0
    return round(actual_dcg / ideal_dcg, 4)


def compute_precision_at_k(is_relevant_flags: Sequence[int], k: int = 10) -> float:
    """Compute fraction of top-k recommendations that are relevant."""
    window = is_relevant_flags[:k]
    if not window:
        return 0.0
    return round(sum(window) / len(window), 4)


def compute_duplicate_rate(cluster_ids: Sequence[str]) -> float:
    """
    Compute duplicate story rate:
    Fraction of articles that share a story_cluster_id with an earlier article.
    Ideal: 0.0 (no redundant stories).
    """
    if not cluster_ids:
        return 0.0
    seen = set()
    duplicates = 0
    for cid in cluster_ids:
        if cid in seen:
            duplicates += 1
        else:
            seen.add(cid)
    return round(duplicates / len(cluster_ids), 4)


def compute_topic_diversity(categories: Sequence[str]) -> Dict[str, float]:
    """
    Compute topic diversity in recommended list:
      - unique_category_ratio: unique categories / total items
      - shannon_entropy: measure of category distribution uniformity
    """
    n = len(categories)
    if n == 0:
        return {"unique_ratio": 0.0, "entropy": 0.0}

    counts: Dict[str, int] = {}
    for cat in categories:
        counts[cat] = counts.get(cat, 0) + 1

    unique_ratio = round(len(counts) / n, 4)

    entropy = 0.0
    for count in counts.values():
        p = count / n
        entropy -= p * math.log2(p)

    return {
        "unique_ratio": unique_ratio,
        "entropy": round(entropy, 4),
    }


def compute_classification_accuracy(
    predicted: Sequence[str],
    expected: Sequence[str],
) -> float:
    """Calculate multi-class accuracy."""
    if not predicted or not expected or len(predicted) != len(expected):
        return 0.0
    correct = sum(1 for p, e in zip(predicted, expected) if p.lower() == e.lower())
    return round(correct / len(predicted), 4)


def evaluate_summary_grounding(summary: str, source_text: str) -> Dict[str, Any]:
    """
    Evaluate factual consistency / hallucination heuristic:
    Checks if capitalized named entities and numbers from summary exist in source text.
    """
    if not summary or not source_text:
        return {"grounded_ratio": 0.0, "unsupported_tokens": []}

    source_lower = source_text.lower()

    # Extract numbers and technical tokens from summary
    summary_tokens = re.findall(r"\b[A-Za-z0-9\.\-]{3,}\b", summary)
    evaluated = [
        t for t in summary_tokens
        if not t.lower() in {"the", "and", "this", "that", "with", "from", "summary", "happened", "matters", "impact"}
    ]

    if not evaluated:
        return {"grounded_ratio": 1.0, "unsupported_tokens": []}

    unsupported = [t for t in evaluated if t.lower() not in source_lower]
    grounded_ratio = round((len(evaluated) - len(unsupported)) / len(evaluated), 4)

    return {
        "grounded_ratio": grounded_ratio,
        "unsupported_tokens": unsupported[:5],
    }
