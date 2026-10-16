"""
Unit tests for utility functions.
No external services required.
"""

from datetime import datetime, timezone
import pytest

from app.utils.text_utils import clean_title, parse_published_date, strip_html, truncate_text
from app.utils.ranking_utils import calculate_score


# ── clean_title ───────────────────────────────────────────────────────────────

def test_clean_title_basic():
    assert clean_title("  Hello   World  ") == "Hello World"

def test_clean_title_newlines():
    assert clean_title("Hello\nWorld") == "Hello World"

def test_clean_title_empty():
    assert clean_title("") == ""

def test_clean_title_none_input():
    assert clean_title(None) == ""

def test_clean_title_multiple_spaces():
    assert clean_title("AI   News    Today") == "AI News Today"


# ── parse_published_date ──────────────────────────────────────────────────────

def test_parse_rfc2822():
    dt = parse_published_date("Mon, 12 Oct 2026 08:00:00 +0530")
    assert dt is not None
    assert dt.tzinfo is not None

def test_parse_iso8601():
    dt = parse_published_date("2026-10-12T08:00:00Z")
    assert dt is not None
    assert dt.tzinfo == timezone.utc

def test_parse_empty_string():
    assert parse_published_date("") is None

def test_parse_none():
    assert parse_published_date(None) is None

def test_parse_invalid():
    assert parse_published_date("not a date at all") is None

def test_parse_returns_utc():
    dt = parse_published_date("2026-10-12T08:00:00+05:30")
    assert dt is not None
    # Should be converted to UTC (08:00 IST = 02:30 UTC)
    assert dt.hour == 2
    assert dt.minute == 30


# ── strip_html ────────────────────────────────────────────────────────────────

def test_strip_html_basic():
    assert strip_html("<p>Hello <b>World</b></p>") == "Hello World"

def test_strip_html_empty():
    assert strip_html("") == ""

def test_strip_html_no_tags():
    assert strip_html("Plain text") == "Plain text"


# ── truncate_text ─────────────────────────────────────────────────────────────

def test_truncate_short():
    assert truncate_text("short", 100) == "short"

def test_truncate_exact():
    text = "a" * 100
    assert truncate_text(text, 100) == text

def test_truncate_long():
    text = "a" * 200
    result = truncate_text(text, 100)
    assert len(result) <= 101  # 100 chars + ellipsis
    assert result.endswith("…")

def test_truncate_empty():
    assert truncate_text("") == ""


# ── calculate_score ───────────────────────────────────────────────────────────

def test_score_fresh_article():
    """Very recent article with AI keywords should score high."""
    article = {
        "clean_title": "OpenAI launches new GPT model",
        "published_dt": datetime.now(timezone.utc),
        "ai_score": 90,
    }
    score = calculate_score(article)
    assert score > 50, f"Expected score > 50, got {score}"

def test_score_old_article():
    """Week-old article without keywords should score low."""
    from datetime import timedelta
    old_dt = datetime.now(timezone.utc).replace(year=2024, month=1, day=1)
    article = {
        "clean_title": "Some random article",
        "published_dt": old_dt,
    }
    score = calculate_score(article)
    assert score < 30, f"Expected score < 30, got {score}"

def test_score_no_date():
    """Article with no date should still get a valid score."""
    article = {
        "clean_title": "Nvidia releases new GPU",
    }
    score = calculate_score(article)
    assert 0 <= score <= 100

def test_score_max_bounded():
    """Score should never exceed 100."""
    article = {
        "clean_title": "openai nvidia google microsoft machine learning AI LLM GPT",
        "published_dt": datetime.now(timezone.utc),
        "ai_score": 100,
    }
    score = calculate_score(article)
    assert score <= 100

def test_score_min_bounded():
    """Score should never be negative."""
    article = {}
    score = calculate_score(article)
    assert score >= 0

def test_score_ai_score_contributes():
    """ai_score should increase the composite score."""
    base = {"clean_title": "tech news", "published_dt": datetime.now(timezone.utc)}
    score_without = calculate_score(base)
    score_with = calculate_score({**base, "ai_score": 100})
    assert score_with > score_without


# ── normalize_url ─────────────────────────────────────────────────────────────

def test_normalize_url_strips_utm():
    from app.utils.text_utils import normalize_url
    url = "https://techcrunch.com/article/?utm_source=twitter&utm_medium=social&utm_campaign=launch"
    assert normalize_url(url) == "https://techcrunch.com/article"


def test_normalize_url_strips_fbclid_and_trailing_slash():
    from app.utils.text_utils import normalize_url
    url = "https://theverge.com/news/123/?fbclid=IwAR234#"
    assert normalize_url(url) == "https://theverge.com/news/123"


def test_normalize_url_preserves_routing_params():
    from app.utils.text_utils import normalize_url
    url = "https://example.com/item?id=456&utm_source=rss"
    assert normalize_url(url) == "https://example.com/item?id=456"


def test_normalize_url_empty_or_invalid():
    from app.utils.text_utils import normalize_url
    assert normalize_url("") == ""
    assert normalize_url(None) == ""


# ── clean_title with publisher suffix ─────────────────────────────────────────

def test_clean_title_publisher_suffix():
    from app.utils.text_utils import clean_title
    raw = "OpenAI Announces GPT-5 - TechCrunch"
    assert clean_title(raw, strip_publisher_suffix=True) == "OpenAI Announces GPT-5"


def test_clean_title_html_entities():
    from app.utils.text_utils import clean_title
    raw = "Nvidia&#8217;s new chip &amp; Google&#39;s AI"
    assert clean_title(raw) == "Nvidia's new chip & Google's AI"


# ── title_similarity & compute_content_hash ───────────────────────────────────

def test_title_similarity_identical():
    from app.utils.text_utils import title_similarity
    t1 = "OpenAI releases GPT-5 reasoning model"
    t2 = "OpenAI releases GPT-5 reasoning model"
    assert title_similarity(t1, t2) == 1.0


def test_title_similarity_near_duplicate():
    from app.utils.text_utils import title_similarity
    t1 = "Google announces Gemini 2.5 Flash with lower latency"
    t2 = "Google launches Gemini 2.5 Flash offering lower latency - TechCrunch"
    sim = title_similarity(t1, t2)
    assert sim >= 0.50, f"Expected similarity >= 0.50, got {sim}"


def test_title_similarity_unrelated():
    from app.utils.text_utils import title_similarity
    t1 = "Apple reports quarterly earnings and iPhone sales"
    t2 = "Zero-day vulnerability discovered in Linux kernel"
    assert title_similarity(t1, t2) < 0.20


def test_content_hash_deterministic():
    from app.utils.text_utils import compute_content_hash
    h1 = compute_content_hash("Title Here", "Some description")
    h2 = compute_content_hash("Title Here", "Some description")
    assert h1 == h2
    assert len(h1) == 64


# ── select_diverse_digest_articles ───────────────────────────────────────────

def test_select_diverse_digest_suppresses_near_duplicates():
    from app.utils.ranking_utils import select_diverse_digest_articles

    articles = [
        {
            "title": "OpenAI releases GPT-5 model today",
            "score": 95.0,
            "category": "AI",
        },
        {
            # Near duplicate story from another publication with slightly lower score
            "title": "OpenAI releases GPT-5 model today to developers",
            "score": 90.0,
            "category": "AI",
        },
        {
            "title": "Major cyberattack hits hospital network",
            "score": 85.0,
            "category": "Cybersecurity",
        },
        {
            "title": "AWS announces new European cloud region",
            "score": 80.0,
            "category": "Cloud",
        },
    ]

    selected = select_diverse_digest_articles(articles, limit=3, near_duplicate_threshold=0.50)
    assert len(selected) == 3
    titles = [a["title"] for a in selected]
    # First OpenAI article should be included
    assert "OpenAI releases GPT-5 model today" in titles
    # Second duplicate should be filtered out!
    assert "OpenAI releases GPT-5 model today to developers" not in titles
    assert "Major cyberattack hits hospital network" in titles
    assert "AWS announces new European cloud region" in titles

