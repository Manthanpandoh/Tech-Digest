"""
Tests for FastAPI endpoints.
All external services are mocked — no real DB, LLM, or network calls.
"""

import pytest
from unittest.mock import patch, MagicMock


# ── Health endpoint ───────────────────────────────────────────────────────────

def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "online"
    assert "version" in data


def test_health_ok(client):
    with patch("main.test_connection", return_value=True), \
         patch("main.get_database") as mock_db:
        mock_db.return_value.name = "techpulse_test"
        r = client.get("/health")
    assert r.status_code in (200, 503)
    data = r.json()
    assert "status" in data
    assert "database" in data
    assert "timestamp" in data


# ── News endpoint ─────────────────────────────────────────────────────────────

def test_get_news_empty(client):
    with patch("app.api.news.get_articles", return_value=[]), \
         patch("app.api.news.count_articles", return_value=0):
        r = client.get("/news")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["data"] == []
    assert data["page"] == 1


def test_get_news_with_articles(client):
    mock_articles = [
        {
            "title": "Test AI Article",
            "clean_title": "Test AI Article",
            "link": "https://example.com/1",
            "source": "TechCrunch",
            "category": "Artificial Intelligence",
            "score": 75.0,
        }
    ]
    with patch("app.api.news.get_articles", return_value=mock_articles), \
         patch("app.api.news.count_articles", return_value=1):
        r = client.get("/news")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert len(data["data"]) == 1
    assert data["data"][0]["title"] == "Test AI Article"


def test_get_news_with_category_filter(client):
    with patch("app.api.news.get_articles", return_value=[]), \
         patch("app.api.news.count_articles", return_value=0):
        r = client.get("/news?category=AI")
    assert r.status_code == 200


def test_get_news_with_search(client):
    with patch("app.api.news.get_articles", return_value=[]), \
         patch("app.api.news.count_articles", return_value=0):
        r = client.get("/news?search=openai")
    assert r.status_code == 200


def test_get_news_pagination_bounds(client):
    with patch("app.api.news.get_articles", return_value=[]), \
         patch("app.api.news.count_articles", return_value=0):
        # page_size too large
        r = client.get("/news?page_size=999")
    assert r.status_code == 422  # Validation error


def test_get_trending(client):
    mock_articles = [
        {"title": f"Article {i}", "link": f"https://example.com/{i}", "score": 80 - i}
        for i in range(5)
    ]
    with patch("app.api.news.get_top_articles", return_value=mock_articles):
        r = client.get("/news/trending")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert len(data["data"]) == 5


# ── Summary endpoint ──────────────────────────────────────────────────────────

def test_summary_success(client):
    with patch("app.api.summary.generate_article_summary", return_value="This is a test summary."):
        r = client.post("/summary", json={
            "title": "OpenAI releases new model",
            "content": "OpenAI today announced a new language model."
        })
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert "summary" in data
    assert data["summary"] == "This is a test summary."


def test_summary_missing_title(client):
    r = client.post("/summary", json={"title": "", "content": "Some content"})
    assert r.status_code == 422


def test_summary_title_too_short(client):
    r = client.post("/summary", json={"title": "AB", "content": "Some content"})
    assert r.status_code == 422


def test_summary_ai_failure(client):
    with patch("app.api.summary.generate_article_summary", side_effect=Exception("AI error")):
        r = client.post("/summary", json={
            "title": "Test title here",
            "content": "Test content"
        })
    assert r.status_code == 500
    assert "failed" in r.json()["detail"].lower()


# ── Analysis endpoint ─────────────────────────────────────────────────────────

def test_analysis_success(client):
    mock_result = {
        "ai_score": 85,
        "category": "AI",
        "sentiment": "Positive",
        "importance": "High",
        "key_insights": ["Insight 1", "Insight 2", "Insight 3"],
    }
    with patch("app.api.analysis.analyze_article", return_value=mock_result):
        r = client.post("/analysis", json={
            "title": "OpenAI launches GPT-5",
            "content": "OpenAI has announced GPT-5 with improved reasoning."
        })
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["analysis"]["ai_score"] == 85
    assert data["analysis"]["category"] == "AI"
    assert data["analysis"]["sentiment"] == "Positive"


def test_analysis_validates_category(client):
    """Invalid category from AI should be coerced to 'Other'."""
    mock_result = {
        "ai_score": 50,
        "category": "InvalidCat",  # should become "Other"
        "sentiment": "Neutral",
        "importance": "Medium",
        "key_insights": ["a", "b", "c"],
    }
    with patch("app.api.analysis.analyze_article", return_value=mock_result):
        r = client.post("/analysis", json={
            "title": "Some tech news story here",
            "content": "content here"
        })
    assert r.status_code == 200
    assert r.json()["analysis"]["category"] == "Other"


# ── Digest endpoint ───────────────────────────────────────────────────────────

def test_digest_not_found(client):
    with patch("app.api.digest.get_digest", return_value=None):
        r = client.get("/digest/latest")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is False


def test_digest_found(client):
    mock_digest = {
        "date": "2026-10-12",
        "article_count": 5,
        "articles": [],
        "whatsapp_sent": False,
        "created_at": "2026-10-12T04:00:00+00:00",
    }
    with patch("app.api.digest.get_digest", return_value=mock_digest):
        r = client.get("/digest/latest")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["date"] == "2026-10-12"


def test_digest_by_invalid_date(client):
    r = client.get("/digest/not-a-date")
    assert r.status_code == 400


# ── Admin endpoint ────────────────────────────────────────────────────────────

def test_admin_collect_without_key(client):
    r = client.post("/admin/collect")
    assert r.status_code == 403


def test_admin_collect_with_wrong_key(client):
    r = client.post("/admin/collect", headers={"X-Admin-Key": "wrong-key"})
    assert r.status_code == 403


def test_admin_collect_with_correct_key(client):
    mock_result = {
        "job_name": "daily_pipeline",
        "success": True,
        "collected": 10,
        "cleaned": 10,
        "ranked": 10,
        "analyzed": 5,
        "digest_date": "2026-10-12",
        "errors": [],
        "started_at": "2026-10-12T04:00:00Z",
        "finished_at": "2026-10-12T04:05:00Z",
        "duration_seconds": 300.0,
    }
    with patch("app.api.admin.run_daily_pipeline", return_value=mock_result):
        r = client.post(
            "/admin/collect",
            headers={"X-Admin-Key": "test-admin-key"}
        )
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
