"""
Unified OpenRouter / LLM service for TechPulse AI.
Provides summary generation and article analysis with retry/backoff.
Includes hallucination-resistant grounded prompts, unified single-call
analysis+summarization to reduce cost & latency, and content-hash caching.
Never returns fabricated data — falls back to safe error states.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config.settings import settings
from app.utils.logging_config import get_logger
from app.utils.text_utils import compute_content_hash

logger = get_logger(__name__)

# ── Content-hash cache for AI responses ─────────────────────────────────────────
# Key: sha256(title|content), Value: Dict result
_ANALYSIS_CACHE: Dict[str, Dict[str, Any]] = {}

# ── OpenRouter client (singleton) ─────────────────────────────────────────────

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
    return _client


# ── Retry decorator ───────────────────────────────────────────────────────────

def _is_retryable_error(exc: BaseException) -> bool:
    if isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        return getattr(exc, "status_code", 0) in (429, 500, 502, 503, 504)
    return False


_retry = retry(
    retry=retry_if_exception(_is_retryable_error),
    stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
    wait=wait_exponential(
        multiplier=settings.LLM_RETRY_WAIT_SECONDS,
        min=settings.LLM_RETRY_WAIT_SECONDS,
        max=60,
    ),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _clean_json_fences(text: str) -> str:
    """Strip markdown code fences and extraneous leading/trailing text."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    # Extract outermost JSON object if surrounded by extra text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0).strip()
    return text.strip()


# ── Public API ────────────────────────────────────────────────────────────────

@_retry
def ask_ai(prompt: str) -> str:
    """
    Send a prompt to the LLM and return the text response.
    Raises on persistent failure — callers should catch and handle.
    """
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert AI Technology News Analyst. "
                    "Analyze technology news accurately, concisely, and factually. "
                    "Base all analysis strictly on facts provided in the text. "
                    "Do not fabricate or speculate on unverified claims."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=settings.LLM_TEMPERATURE_SUMMARY,
        max_tokens=settings.LLM_MAX_TOKENS_SUMMARY,
    )
    return response.choices[0].message.content or ""


def generate_article_summary(title: str, content: str) -> str:
    """
    Generate a structured news summary grounded in article content.
    Returns a fallback string on failure.
    """
    # Check cache
    cache_key = f"summary:{compute_content_hash(title, content)}"
    if cache_key in _ANALYSIS_CACHE:
        return _ANALYSIS_CACHE[cache_key]["summary"]

    safe_content = (content or "").strip()[:2000]

    prompt = f"""You are an AI Technology News Analyst.

Analyze the following technology news article. Ground all points strictly in the provided text.
Do not invent facts, numbers, dates, or specifications not found in the article.

TITLE:
{title}

ARTICLE:
{safe_content if safe_content else "No additional article text provided. Summarize based on the title."}

Structure your response exactly as follows:

Summary:
Explain the article in simple terms (2-3 sentences).

What happened:
Explain the main event or announcement (1-2 sentences).

Why it matters:
Explain why this development is important (1-2 sentences).

Impact:
Explain the potential impact on technology, companies, developers or users (2-3 sentences).
"""
    try:
        summary_text = ask_ai(prompt)
        _ANALYSIS_CACHE[cache_key] = {"summary": summary_text}
        return summary_text
    except Exception as exc:
        logger.error("generate_article_summary failed: %s", type(exc).__name__)
        return (
            f"Summary unavailable. AI service temporarily unreachable.\n\n"
            f"Article: {title}"
        )


@_retry
def analyze_article(title: str, content: str) -> Dict[str, Any]:
    """
    Analyse an article and return a validated dict with AI scores.
    Returns a safe fallback dict on persistent failure.
    """
    safe_content = (content or "")[:2000]
    cache_key = f"analysis:{compute_content_hash(title, content)}"
    if cache_key in _ANALYSIS_CACHE:
        return _ANALYSIS_CACHE[cache_key]

    prompt = f"""You are an expert technology news analyst.

Analyse the following technology news article. Base your analysis strictly on the content provided.

TITLE:
{title}

ARTICLE CONTENT:
{safe_content if safe_content else "Title only provided."}

Return ONLY valid JSON with no markdown fences and no extra text.

Use EXACTLY this structure:

{{
    "ai_score": 0,
    "category": "AI",
    "sentiment": "Neutral",
    "importance": "Medium",
    "key_insights": [
        "Insight 1",
        "Insight 2",
        "Insight 3"
    ]
}}

Rules:
- ai_score: integer 0–100 reflecting overall technology significance.
- category: exactly one of: AI, Cloud, Cybersecurity, Programming, Google, Microsoft, Apple, Other
- sentiment: exactly one of: Positive, Negative, Neutral
- importance: exactly one of: Low, Medium, High
- key_insights: exactly 3 concise factual strings grounded in the text.
"""

    client = _get_client()
    response = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional technology news classification AI. "
                    "Always return valid JSON when requested. No markdown fences."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=settings.LLM_TEMPERATURE_ANALYSIS,
        max_tokens=settings.LLM_MAX_TOKENS_ANALYSIS,
    )

    raw = response.choices[0].message.content or ""
    cleaned = _clean_json_fences(raw)
    data = json.loads(cleaned)

    # Validate and normalise fields
    allowed_categories = {"AI", "Cloud", "Cybersecurity", "Programming",
                          "Google", "Microsoft", "Apple", "Other"}
    allowed_sentiments = {"Positive", "Negative", "Neutral"}
    allowed_importance = {"Low", "Medium", "High"}

    ai_score = data.get("ai_score", 50)
    try:
        ai_score = int(ai_score)
    except (ValueError, TypeError):
        ai_score = 50
    ai_score = max(0, min(100, ai_score))

    result = {
        "ai_score": ai_score,
        "category": data.get("category", "Other") if data.get("category") in allowed_categories else "Other",
        "sentiment": data.get("sentiment", "Neutral") if data.get("sentiment") in allowed_sentiments else "Neutral",
        "importance": data.get("importance", "Medium") if data.get("importance") in allowed_importance else "Medium",
        "key_insights": data.get("key_insights", [])[:3],
    }
    _ANALYSIS_CACHE[cache_key] = result
    return result


def analyze_article_safe(title: str, content: str) -> Dict[str, Any]:
    """
    Wrapper that catches all exceptions and returns a documented fallback.
    Use this in batch pipelines to avoid stopping on a single failure.
    """
    try:
        return analyze_article(title, content)
    except json.JSONDecodeError:
        logger.warning("analyze_article: JSON parse failed for: %s", title[:60])
    except Exception as exc:
        logger.error("analyze_article: %s for: %s", type(exc).__name__, title[:60])

    return {
        "ai_score": 0,
        "category": "Other",
        "sentiment": "Neutral",
        "importance": "Medium",
        "key_insights": ["Analysis unavailable", "AI service unreachable", "Try again later"],
        "analysis_error": True,
    }


@_retry
def analyze_and_summarize_article(title: str, content: str) -> Dict[str, Any]:
    """
    Consolidated single LLM call for both structured analysis and grounded summary.
    Cuts API requests and latency by 50% compared to dual separate calls.
    Returns:
      {
        "ai_score": int,
        "category": str,
        "sentiment": str,
        "importance": str,
        "key_insights": List[str],
        "summary": str,
      }
    """
    cache_key = f"unified:{compute_content_hash(title, content)}"
    if cache_key in _ANALYSIS_CACHE:
        return _ANALYSIS_CACHE[cache_key]

    safe_content = (content or "").strip()[:2000]

    prompt = f"""You are an expert AI Technology News Analyst.

Analyze and summarize the following technology news article. Ground all claims strictly in the text.
Do not hallucinate dates, figures, or partnerships not present in the article.

TITLE:
{title}

ARTICLE CONTENT:
{safe_content if safe_content else "Title only provided."}

Return ONLY valid JSON with no markdown fences and no extra text.

Use EXACTLY this JSON structure:
{{
    "ai_score": 75,
    "category": "AI",
    "sentiment": "Positive",
    "importance": "Medium",
    "key_insights": [
        "First key insight grounded in the article",
        "Second key insight grounded in the article",
        "Third key insight grounded in the article"
    ],
    "summary": "Summary:\nExplain the article in simple terms (2-3 sentences).\n\nWhat happened:\nExplain the main event or announcement (1-2 sentences).\n\nWhy it matters:\nExplain why this development is important (1-2 sentences).\n\nImpact:\nExplain potential industry or user impact (2-3 sentences)."
}}

Rules:
- ai_score: integer 0–100 reflecting genuine technological and industry significance.
- category: exactly one of: AI, Cloud, Cybersecurity, Programming, Google, Microsoft, Apple, Other
- sentiment: exactly one of: Positive, Negative, Neutral
- importance: exactly one of: Low, Medium, High
- key_insights: exactly 3 concise factual bullet points.
- summary: structured text with Summary, What happened, Why it matters, and Impact sections.
"""

    client = _get_client()
    response = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional technology news analyst. "
                    "Always output strictly valid JSON without markdown wrapping. "
                    "Ground all summaries and ratings strictly on the input text."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=settings.LLM_TEMPERATURE_ANALYSIS,
        max_tokens=settings.LLM_MAX_TOKENS_SUMMARY + settings.LLM_MAX_TOKENS_ANALYSIS,
    )

    raw = response.choices[0].message.content or ""
    cleaned = _clean_json_fences(raw)
    data = json.loads(cleaned)

    allowed_categories = {"AI", "Cloud", "Cybersecurity", "Programming",
                          "Google", "Microsoft", "Apple", "Other"}
    allowed_sentiments = {"Positive", "Negative", "Neutral"}
    allowed_importance = {"Low", "Medium", "High"}

    ai_score = data.get("ai_score", 50)
    try:
        ai_score = int(ai_score)
    except (ValueError, TypeError):
        ai_score = 50
    ai_score = max(0, min(100, ai_score))

    summary = (data.get("summary") or "").strip()
    if not summary:
        summary = f"Summary: {title}"

    result = {
        "ai_score": ai_score,
        "category": data.get("category", "Other") if data.get("category") in allowed_categories else "Other",
        "sentiment": data.get("sentiment", "Neutral") if data.get("sentiment") in allowed_sentiments else "Neutral",
        "importance": data.get("importance", "Medium") if data.get("importance") in allowed_importance else "Medium",
        "key_insights": data.get("key_insights", [])[:3],
        "summary": summary,
    }
    _ANALYSIS_CACHE[cache_key] = result
    return result


def analyze_and_summarize_safe(title: str, content: str) -> Dict[str, Any]:
    """
    Fault-tolerant wrapper for unified analysis and summarization.
    Catches all exceptions, logging them cleanly, and returns a documented fallback.
    """
    try:
        return analyze_and_summarize_article(title, content)
    except json.JSONDecodeError:
        logger.warning("analyze_and_summarize: JSON parse failed for: %s", title[:60])
    except Exception as exc:
        status_info = f" (status {getattr(exc, 'status_code', 'unknown')})" if hasattr(exc, "status_code") else ""
        logger.error("analyze_and_summarize: %s%s: %s for: %s", type(exc).__name__, status_info, exc, title[:60])

    return {
        "ai_score": 0,
        "category": "Other",
        "sentiment": "Neutral",
        "importance": "Medium",
        "key_insights": ["Analysis unavailable", "AI service unreachable", "Try again later"],
        "summary": f"Summary unavailable for: {title}",
        "analysis_error": True,
    }
