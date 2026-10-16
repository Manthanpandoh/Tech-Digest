# TechPulse AI — Architecture & Technical Design

---

## 1. System Overview

TechPulse AI is an agentic, production-engineered news intelligence platform. It autonomously collects technology news from diverse RSS publications concurrently, cleans and normalizes content, deduplicates syndicated stories, evaluates articles via OpenRouter using Google Gemini 2.5 Flash, computes calibrated multi-factor ranking scores, curates a diverse top-10 daily digest, and delivers it via WhatsApp.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL SOURCES                               │
│      Google News RSS · TechCrunch · The Verge · Wired · Ars Technica        │
│                         MIT Tech Review (+ more)                            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │  Concurrent feedparser (Bounded Pool)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       BACKEND (FastAPI / Python 3.12)                       │
│                                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐  │
│  │  Collector   │──▶│   Cleaner    │──▶│    Ranker    │──▶│   Analyser   │  │
│  │  Agent (5x)  │   │  Agent (URL) │   │  Agent (Decay│   │  Agent (LLM) │  │
│  └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘  │
│         │                  │                  │                  │          │
│         └──────────────────┴──────────────────┴──────────────────┘          │
│                                      │                                      │
│                            ┌─────────▼──────────┐                           │
│                            │   Daily Pipeline   │                           │
│                            │    Orchestrator    │                           │
│                            └─────────┬──────────┘                           │
│                                      │                                      │
│  ┌───────────────────────────────────▼───────────────────────────────────┐  │
│  │                      FastAPI REST API Services                        │  │
│  │   GET  /news            GET  /news/trending                           │  │
│  │   POST /summary         POST /analysis                                │  │
│  │   GET  /digest/latest   GET  /digest/{date}                           │  │
│  │   POST /admin/collect   GET  /admin/status                            │  │
│  │   GET  /health          GET  /                                        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │
           ┌────────────────┼────────────────┐
           │                │                │
           ▼                ▼                ▼
   ┌──────────────┐  ┌─────────────┐  ┌──────────────────┐
   │ MongoDB Atlas│  │  OpenRouter │  │ WhatsApp Business│
   │  (Storage)   │  │ (Gemini 2.5)│  │    Cloud API     │
   └──────────────┘  └─────────────┘  └──────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (React 19 / Vite / Tailwind)                  │
│    News Feed · Category Filter · Debounced Search · Live Trending Sidebar   │
│    AI Summary Modal · Pre-computed Cache · Skeleton Loading · Pagination    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Scheduled Automation (Render Cron)

```
22:30 UTC (4:00 AM IST)          00:30 UTC (6:00 AM IST)
        │                                 │
        ▼                                 ▼
 collect_job.py                  send_digest_job.py
  1. Concurrent RSS collection    1. Load today's India-date digest
  2. Normalize & canonicalize     2. Validate contents & recipient consent
  3. Deduplicate (link + hash)    3. Format bounded WhatsApp message
  4. Initial rank (freshness)     4. Dispatch via Meta Cloud API / Dry-run
  5. Unified AI analysis+summary  5. Mark digest sent & log delivery
  6. Re-rank with AI score
  7. Filter near-duplicates
  8. Save top-10 diverse digest
```

---

## 3. Data Flow & Agent Pipeline

### 3.1 Concurrent Collection Agent (`collector_agent.py`)
- Employs `concurrent.futures.ThreadPoolExecutor(max_workers=5)` to fetch 10 feeds simultaneously.
- Reduces collection time from ~16.2s to ~2.4s (6.75x speedup).
- Each feed is isolated with independent timeout guards (`RSS_FEED_TIMEOUT_SECONDS=15`).

### 3.2 Cleaning & Normalization (`cleaning_agent.py`, `text_utils.py`)
- **URL Normalization:** Strips marketing tracking parameters (`utm_*`, `fbclid`, `gclid`, `mc_eid`, `ref`, etc.), lowercases schemes/hosts, and removes fragments to prevent duplicate storage.
- **Title Cleaning:** Decodes HTML entities, normalizes typography (curly quotes to ASCII), and strips publisher suffixes (e.g. ` - TechCrunch`).
- **Date Normalization:** Parses RFC 2822 and ISO 8601 into timezone-aware UTC `datetime` objects.

### 3.3 Unified AI Analysis & Summarization (`ai_service.py`, `summary_agent.py`)
- **Consolidated Single-Call Architecture:** Combines semantic categorization, sentiment, editorial importance, 3 key insights, and structured summary into a single JSON schema.
- **50% Cost & Latency Reduction:** Halves LLM network roundtrips from 2 to 1 per article.
- **Content-Hash Caching:** Employs SHA-256 `title|content` hashing (`compute_content_hash`) to avoid redundant inference on unchanged articles.
- **Anti-Hallucination Grounding:** System prompt enforces factual consistency strictly against the article body.

### 3.4 Multi-Factor Ranking Engine (`ranking_utils.py`)
$$\text{Score} = S_{\text{recency}} + S_{\text{source}} + S_{\text{keywords}} + S_{\text{ai}}$$
Where:
1. **Continuous Exponential Recency Decay (0–35 pts):**
   $$S_{\text{recency}} = 35 \times 2^{-\frac{\text{age\_hours}}{24}}$$
2. **Source Authority Tiers (0–10 pts):**
   - Tier 1 (+10 pts): MIT Technology Review, Ars Technica, Wired, Google AI Blog, TechCrunch
   - Tier 2 (+5–6 pts): The Verge, Google Cloud/ML Blogs
   - Tier 3 (+2 pts): Syndicated aggregators
3. **High-Signal Tech Keywords (0–20 pts):**
   - Weighted by domain relevance (OpenAI, Gemini, Claude, Nvidia, Kubernetes, Zero-day).
4. **AI Evaluation (0–35 pts):**
   - Scaled `ai_score` (0–25 pts) + Editorial Importance Bonus (High: +10, Medium: +5, Low: +0).
Total bounded in $[0.0, 100.0]$.

### 3.5 Diversity & Duplicate Story Suppression (`select_diverse_digest_articles`)
- Employs hybrid Jaccard & Szymkiewicz-Simpson Overlap similarity:
  $$\text{Overlap}(A, B) = \frac{|A \cap B|}{\min(|A|, |B|)}$$
- Suppresses near-duplicate syndicated coverage ($\ge 0.40$ similarity) from the top-10 digest.
- Enforces category caps ($\le 3$ articles per category) to ensure broad technology coverage.

---

## 4. Database Collections & Indexes

| Collection | Key Purpose | Production Indexes |
|---|---|---|
| `articles` | Normalized news stories | `link` (unique), `canonical_link` (sparse), `score` (desc), `created_at` (desc), `category`, `status` |
| `digests` | Daily Asia/Kolkata top-10 digests | `date` (unique) |
| `job_history` | Audit log of pipeline executions | `started_at` (desc) |
| `whatsapp_log` | Meta Graph delivery receipts | `sent_at` (desc) |
| `pipeline_locks` | Distributed concurrency guard | `job_name` (unique) |

---

## 5. Security & Production Reliability

- **Secret Zero-Exposure:** Credentials exist only in `.env` files (gitignored).
- **Log Sanitization:** MongoDB URIs and authorization tokens are masked prior to emission.
- **Admin Authentication:** Endpoints under `/admin/*` require the `X-Admin-Key` header.
- **CORS Configuration:** Configurable via `FRONTEND_ORIGIN` for strict cross-origin security.
- **WhatsApp Safety:** Default `WHATSAPP_DRY_RUN=true` prevents unauthorized automated dispatch.
- **Local Fallback Mode:** `USE_MOCK_DB=true` enables local execution and offline testing when external Atlas DNS is temporarily unreachable.
