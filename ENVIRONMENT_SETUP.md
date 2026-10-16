# TechPulse AI — Environment Setup

---

## Backend (`backend/.env`)

Copy `backend/.env.example` to `backend/.env` and fill in your values.

```bash
cd backend
copy .env.example .env   # Windows
```

### Required Variables

| Variable | Example | Description |
|---|---|---|
| `MONGODB_URI` | `mongodb+srv://user:pass@cluster.mongodb.net/` | Atlas connection string |
| `DATABASE_NAME` | `techpulse_ai` | MongoDB database name |
| `OPENROUTER_API_KEY` | `your_openrouter_api_key_here` | OpenRouter key |
| `MODEL_NAME` | `google/gemini-2.5-flash` | LLM model |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS origin |
| `ADMIN_API_KEY` | `my-secret-key` | Protects `/admin/*` routes |

### Optional Variables (defaults shown)

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter endpoint |
| `DEBUG` | `false` | Enables debug logging |
| `LLM_MAX_RETRIES` | `3` | LLM retry attempts |
| `LLM_TIMEOUT_SECONDS` | `60` | LLM request timeout |
| `MAX_ARTICLES_PER_FEED` | `20` | Articles fetched per RSS feed |
| `MAX_ARTICLES_TO_ANALYZE` | `50` | Articles analysed per pipeline run |
| `TOP_ARTICLES_FOR_DIGEST` | `10` | Articles in daily digest |
| `TIMEZONE` | `Asia/Kolkata` | Scheduling timezone |
| `WHATSAPP_DRY_RUN` | `true` | Safe default — no messages sent |
| `USE_MOCK_DB` | `false` | In-memory MongoDB mock for offline runs |

### WhatsApp Variables (only needed for live delivery)

| Variable | Description |
|---|---|
| `WHATSAPP_ACCESS_TOKEN` | Meta permanent access token |
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp Business phone number ID |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | WhatsApp Business Account ID |
| `WHATSAPP_TEMPLATE_NAME` | Approved template name |
| `WHATSAPP_API_VERSION` | Meta Graph API version (default: `v22.0`) |
| `WHATSAPP_RECIPIENTS` | Comma-separated E.164 numbers |

---

## Frontend (`frontend/.env`)

```bash
cd frontend
copy .env.example .env   # Windows
```

| Variable | Local Dev | Production |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | `https://your-backend.onrender.com` |

---

## Security Checklist

- [ ] `backend/.env` is listed in `.gitignore` — never commit it
- [ ] `frontend/.env` is listed in `.gitignore` — never commit it  
- [ ] `ADMIN_API_KEY` is changed from the default `change-me-in-production`
- [ ] MongoDB credentials are not shared publicly
- [ ] OpenRouter key is not exposed in frontend code
- [ ] WhatsApp token is not logged or returned in API responses
- [ ] `WHATSAPP_DRY_RUN=true` until fully set up

---

## Rotating Exposed Credentials

If any credential has been committed to git or otherwise exposed:

1. **MongoDB**: Go to Atlas > Database Access > Edit user > Change password
2. **OpenRouter**: Go to openrouter.ai > Keys > Revoke and create new
3. **WhatsApp**: Go to Meta Business > System Users > Revoke token

After rotating, update your `.env` and all hosting platform environment variables.
