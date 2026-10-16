# TechPulse AI — Testing Guide

---

## Automated Test Suite

### Run all tests (no credentials needed)

```bash
cd backend
venv\Scripts\activate       # Windows
python -m pytest tests/ -v
```

**Result: 64 passed** (verified 2026-10-16, Python 3.12.10)

All external services are mocked — no MongoDB, OpenRouter, or WhatsApp calls are made.

### Test coverage summary

| File | Tests | What is covered |
|---|---|---|
| `tests/test_api.py` | 20 | All REST endpoints — health, news, summary, analysis, digest, admin auth |
| `tests/test_utils.py` | 35 | `clean_title`, `parse_published_date`, `strip_html`, `truncate_text`, `calculate_score`, `normalize_url`, `title_similarity`, `compute_content_hash`, `select_diverse_digest_articles` |
| `tests/test_whatsapp.py` | 9 | Message formatting, dry-run, missing credentials, phone number validation |

### Run a specific test file

```bash
python -m pytest tests/test_api.py -v
python -m pytest tests/test_utils.py -v
python -m pytest tests/test_whatsapp.py -v
```

### Run the Benchmark Evaluation Suite

```bash
python app/evaluation/run_benchmark.py
```
Outputs NDCG@10, Precision@10, duplicate collision rate, topic diversity entropy, and AI cost metrics.

---

## Manual Integration Tests (requires real credentials)

These tests hit your actual MongoDB Atlas cluster and OpenRouter API.
They consume API credits and write to your database.

### Prerequisites

```bash
cd backend
# Confirm .env is populated
type .env   # Windows — verify all required values are present
```

### Test 1: MongoDB connectivity

```bash
python test_mongo.py
```
Expected: `Pinging MongoDB... Connected Successfully`

### Test 2: Full pipeline dry-run (no WhatsApp send)

```bash
python -m app.scheduler.collect_job
```

Expected log output (abbreviated):
```
=== Collector Agent started ===
Fetching feed: Google AI Blog...
Feed Google AI Blog: 20 entries
...
=== Collector done: N/10 feeds ok, X new articles saved ===
=== Cleaning Agent started ===
...
=== Ranking Agent started ===
...
=== Summary/Analysis Agent started ===
...
=== Daily Pipeline finished in Xs — success=True ===
```

### Test 3: WhatsApp dry-run (no message sent)

```bash
python -m app.scheduler.send_digest_job
```

Expected: message preview in logs, `dry_run: true`, exit 0

### Test 4: API endpoints (backend must be running)

Start the backend:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Then in a second terminal:
```bash
# Health check
curl http://localhost:8000/health

# Paginated news feed
curl http://localhost:8000/news

# Top trending articles
curl "http://localhost:8000/news/trending?limit=5"

# Latest digest
curl http://localhost:8000/digest/latest

# AI summary
curl -X POST http://localhost:8000/summary \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"OpenAI launches GPT-5\",\"content\":\"OpenAI announced a new model.\"}"

# Admin trigger (replace YOUR_KEY with value of ADMIN_API_KEY in .env)
curl -X POST "http://localhost:8000/admin/collect" \
  -H "X-Admin-Key: YOUR_KEY"
```

### Test 5: Frontend build

```bash
cd frontend
npm install
npm run build
```

Expected: Build succeeds, output in `frontend/dist/`.

---

## Known Test Limitations

| Limitation | Reason |
|---|---|
| No live MongoDB tests in CI | Requires Atlas credentials — safe to exclude from automated runs |
| No live LLM tests in CI | Each run consumes paid API credits |
| No live WhatsApp tests | Requires verified Business account + recipient opt-in |
| No frontend component tests | Vitest not yet set up — can be added as a follow-up |
| `/admin/collect` runs synchronously | May approach Render free-tier timeout for large feeds |

---

## Adding New Tests

Tests live in `backend/tests/`. The `conftest.py` sets safe mock env vars and provides a `client` fixture (FastAPI `TestClient`). Add new test files following the existing patterns — mock all external calls with `unittest.mock.patch`.
