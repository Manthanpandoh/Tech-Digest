# TechPulse AI

An agentic AI platform that automatically collects real-time technology news, analyses and ranks articles using AI, generates daily digests, and delivers them via WhatsApp.

---

## Features

| Feature | Status |
|---|---|
| Concurrent RSS collection (10 sources, ~2.4s) | ✅ Complete (6.75x speedup) |
| URL canonicalization & tracking parameter stripping | ✅ Complete |
| Hybrid near-duplicate story detection | ✅ Complete (0% duplicate digest rate) |
| Unified AI analysis & grounded summary | ✅ Complete (50% LLM cost reduction) |
| SHA-256 Content-hash inference caching | ✅ Complete |
| Calibrated multi-factor ranker with exponential decay | ✅ Complete |
| Story diversity & category balancing in digest | ✅ Complete |
| Automated scheduling (4 AM and 6 AM IST) | ✅ Verified entry points |
| WhatsApp Business delivery with safe dry-run | ✅ Complete |
| Paginated REST API with search, filter, and trending | ✅ Complete |
| React 19 / Vite / Tailwind frontend | ✅ Production-built in 8s |
| 64 automated backend unit & API tests | ✅ 100% passing |
| Empirical benchmark suite (`BENCHMARK_REPORT.md`) | ✅ Validated |

---

## Architecture

```
Frontend (Vercel)          Backend (Render)           Data / AI
┌──────────────┐           ┌────────────────────┐     ┌──────────────────┐
│ React + Vite │ ─ HTTPS ─▶│ FastAPI / Uvicorn  │────▶│ MongoDB Atlas    │
│ Tailwind CSS │           │                    │     └──────────────────┘
└──────────────┘           │  /news             │     ┌──────────────────┐
                           │  /summary          │────▶│ OpenRouter       │
                           │  /analysis         │     │ (Gemini 2.5 Flash│
                           │  /digest           │     │  via OpenAI SDK) │
                           │  /admin            │     └──────────────────┘
                           └────────────────────┘     ┌──────────────────┐
                                    │                  │ WhatsApp Business│
                           ┌────────┴───────┐          │ Cloud API        │
                           │ Render Cron    │─────────▶└──────────────────┘
                           │  collect_job   │ 4:00 AM IST
                           │  send_digest   │ 6:00 AM IST
                           └────────────────┘
```

---

## Quick Start (Local)

### Prerequisites

- Python 3.12
- Node.js 18+
- MongoDB Atlas account
- OpenRouter API key

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env         # Fill in your values
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000/docs` for the interactive API documentation.

### Frontend

```bash
cd frontend
npm install
copy .env.example .env         # Set VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Visit `http://localhost:5173`.

---

## Running the News Pipeline Manually

```bash
cd backend
venv\Scripts\activate
python -m app.scheduler.collect_job      # Collect, analyse, rank, build digest
python -m app.scheduler.send_digest_job  # Send digest via WhatsApp (dry-run by default)
```

---

## Running Tests

```bash
cd backend
venv\Scripts\activate
python -m pytest tests/ -v
```

Expected: **64 passed** (no external services required — all mocked).

---

## Repository Structure

```
TechPulse-AI/
├── backend/
│   ├── main.py                     FastAPI application entry point
│   ├── requirements.txt            Python dependencies
│   ├── .env.example                Environment variable template
│   ├── app/
│   │   ├── agents/                 Collector, Cleaner, Ranker, Summariser
│   │   ├── api/                    FastAPI routers (news, summary, analysis, digest, admin)
│   │   ├── config/settings.py      Centralised env-based configuration
│   │   ├── database/               MongoDB connection + repository
│   │   ├── models/schemas.py       Pydantic request/response models
│   │   ├── scheduler/              Cron job entry points
│   │   ├── services/               AI, News, WhatsApp services
│   │   ├── utils/                  Logging, text, ranking utilities
│   │   └── workflows/pipeline.py   Daily pipeline orchestration
│   └── tests/                      pytest test suite
└── frontend/
    ├── src/
    │   ├── components/             UI components
    │   ├── pages/Home.jsx          Main page
    │   └── services/api.js         Axios client (env-configured)
    └── .env.example                Frontend env template
```

---

## Environment Variables

See `backend/.env.example` and `frontend/.env.example` for the complete reference.

Key variables:

| Variable | Required | Description |
|---|---|---|
| `MONGODB_URI` | Yes | MongoDB Atlas connection string |
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key |
| `MODEL_NAME` | Yes | LLM model identifier |
| `FRONTEND_ORIGIN` | Yes | CORS allowed origin(s) |
| `ADMIN_API_KEY` | Yes | Protects `/admin` endpoints |
| `WHATSAPP_ACCESS_TOKEN` | For live send | WhatsApp Business token |
| `WHATSAPP_PHONE_NUMBER_ID` | For live send | WhatsApp phone number ID |
| `WHATSAPP_DRY_RUN` | — | Default: `true` (safe) |
| `VITE_API_BASE_URL` | Yes (frontend) | Backend URL |

---

## Security Notes

- The `.env` file is gitignored and must never be committed.
- The live credentials in `backend/.env` have not been committed to git (verified).
- **Rotate your MongoDB and OpenRouter credentials** if you believe they may have been exposed.
- Admin endpoints (`/admin/*`) require the `X-Admin-Key` header.
- WhatsApp delivery defaults to dry-run — set `WHATSAPP_DRY_RUN=false` only after verifying credentials.

---

## Known Limitations

- No trained ML ranking model exists — a documented baseline score is used instead.
- Gemini SDK (`gemini_service.py`) has been removed — OpenRouter covers AI needs.
- WhatsApp live delivery requires a verified Meta Business account and approved message templates.
- The `/admin/collect` endpoint triggers the full pipeline synchronously — for large collections this may timeout on Render free tier. Consider background tasks for production.

---

## Licence

Private project — all rights reserved.
