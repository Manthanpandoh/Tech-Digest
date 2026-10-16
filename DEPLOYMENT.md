# TechPulse AI — Deployment Guide

---

## Overview

| Component | Platform | Notes |
|---|---|---|
| Backend API | Render Web Service | Python / FastAPI / Uvicorn |
| Cron Job 1 (4 AM IST) | Render Cron Job | Collect + Analyse + Digest |
| Cron Job 2 (6 AM IST) | Render Cron Job | WhatsApp delivery |
| Frontend | Vercel | React / Vite / Tailwind |
| Database | MongoDB Atlas | Cloud-hosted |
| AI | OpenRouter | `google/gemini-2.5-flash` |
| Messaging | WhatsApp Business Cloud API | Meta Graph API |

---

## 1. MongoDB Atlas

1. Log in at https://cloud.mongodb.com
2. Create a free M0 cluster (or use your existing `TechPulseCluster`)
3. Create a database user with **Read and Write** to any database
4. Under Network Access, add `0.0.0.0/0` (allow all) or whitelist Render's IPs
5. Click **Connect > Connect your application** and copy the connection string
6. Replace `<password>` with your database user's password
7. Set `MONGODB_URI` in your Render environment variables

#### Troubleshooting Atlas DNS Errors
If you see `ConfigurationError: The DNS query name does not exist`:
- **Cluster Paused:** Free-tier (M0) Atlas clusters are automatically paused by MongoDB after 60 days of inactivity. Log into Atlas and click **Resume Cluster**.
- **Recreated Cluster:** If the cluster was deleted and recreated, Atlas generates a new hostname. Copy the fresh connection string from **Connect > Drivers**.
- **Network / DNS Issues:** Ensure Network Access includes `0.0.0.0/0` (or your IP).
- **Offline / Local Testing Fallback:** You can run the entire pipeline and test suite offline by setting `USE_MOCK_DB=true` in `backend/.env`.

---

## 2. Render Backend Web Service

### Repository settings

| Field | Value |
|---|---|
| Root directory | `backend` |
| Runtime | `Python 3.12` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |

### Environment variables to set in Render dashboard

```
MONGODB_URI=mongodb+srv://...
DATABASE_NAME=techpulse_ai
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=google/gemini-2.5-flash
FRONTEND_ORIGIN=https://your-app.vercel.app
ADMIN_API_KEY=<strong-random-secret>
WHATSAPP_DRY_RUN=true
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_RECIPIENTS=
TIMEZONE=Asia/Kolkata
```

### Health check

Set Render health check path to: `/health`

### After deployment

Test these URLs:
- `https://your-backend.onrender.com/` — should return `{"status":"online"}`
- `https://your-backend.onrender.com/health` — should show `"database":"connected"`
- `https://your-backend.onrender.com/docs` — OpenAPI documentation

---

## 3. Render Cron Jobs

Create **two separate** Render Cron Jobs pointing to the same repository.

### Cron Job 1 — News Collection + Digest

| Field | Value |
|---|---|
| Root directory | `backend` |
| Runtime | Python 3.12 |
| Build command | `pip install -r requirements.txt` |
| Command | `python -m app.scheduler.collect_job` |
| Schedule | `30 22 * * *` (= 4:00 AM IST, UTC-based) |

### Cron Job 2 — WhatsApp Digest Delivery

| Field | Value |
|---|---|
| Root directory | `backend` |
| Runtime | Python 3.12 |
| Build command | `pip install -r requirements.txt` |
| Command | `python -m app.scheduler.send_digest_job` |
| Schedule | `30 0 * * *` (= 6:00 AM IST, UTC-based) |

### Manual test (from local machine)

```bash
cd backend
# Test collection (safe — no messages sent, dry-run digest)
python -m app.scheduler.collect_job

# Test delivery (dry-run by default)
python -m app.scheduler.send_digest_job

# Force live send (only after credentials configured)
WHATSAPP_DRY_RUN=false python -m app.scheduler.send_digest_job
```

### Timezone reference

| IST Time | UTC Time | Cron (UTC) |
|---|---|---|
| 4:00 AM IST (collect) | 22:30 UTC (previous day) | `30 22 * * *` |
| 6:00 AM IST (send) | 00:30 UTC | `30 0 * * *` |

---

## 4. Vercel Frontend

1. Import the repository in Vercel
2. Set the **Root Directory** to `frontend`
3. Vite is auto-detected; build command: `npm run build`, output: `dist`
4. Add environment variable:

```
VITE_API_BASE_URL=https://your-backend.onrender.com
```

5. Deploy and test at your Vercel URL

---

## 5. WhatsApp Business Platform

### Prerequisites (you must complete these manually)

- [ ] A Meta Business account at https://business.facebook.com
- [ ] A WhatsApp Business Account (WABA) verified
- [ ] A phone number added and verified as a WhatsApp Business number
- [ ] A message template named `techpulse_digest` approved by Meta
  - The template must be in the **UTILITY** or **MARKETING** category
  - For plain text messages, a simple body template is sufficient
- [ ] A System User or App with `whatsapp_business_messaging` permission
- [ ] A permanent access token generated for the System User

### Configuration steps

1. Go to https://developers.facebook.com/apps
2. Create an app or use an existing one
3. Add **WhatsApp** product
4. Note your **Phone Number ID** and **WhatsApp Business Account ID**
5. Generate a permanent token via your Business System User
6. Set these environment variables in Render:

```
WHATSAPP_ACCESS_TOKEN=your_permanent_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_BUSINESS_ACCOUNT_ID=your_waba_id
WHATSAPP_TEMPLATE_NAME=techpulse_digest
WHATSAPP_API_VERSION=v22.0
WHATSAPP_DRY_RUN=false       # Only after full setup
WHATSAPP_RECIPIENTS=91XXXXXXXXXX,91XXXXXXXXXX
```

7. Test with dry-run first:
```bash
python -m app.scheduler.send_digest_job
```

8. Verify the formatted message in the logs before setting `WHATSAPP_DRY_RUN=false`

---

## 6. Environment Variable Mapping (Render vs Vercel)

| Variable | Platform | Classification | Purpose / Setting Guide |
|---|---|---|---|
| `MONGODB_URI` | **Render Only** | Secret | Full Atlas URI with user & password. Never put in Vercel. |
| `DATABASE_NAME` | **Render Only** | Config | Value: `techpulse_ai`. |
| `USE_MOCK_DB` | **Render Only** | Config | Value: `false` (enforces real Atlas connectivity). |
| `OPENROUTER_API_KEY` | **Render Only** | Secret | OpenRouter API Key for Gemini-2.5-flash. |
| `OPENROUTER_BASE_URL`| **Render Only** | Config | Value: `https://openrouter.ai/api/v1`. |
| `MODEL_NAME` | **Render Only** | Config | Value: `google/gemini-2.5-flash`. |
| `FRONTEND_ORIGIN` | **Render Only** | Config | Your production Vercel URL, e.g. `https://techpulse-ai.vercel.app`. |
| `ADMIN_API_KEY` | **Render Only** | Secret | Random alphanumeric secret for manual pipeline triggers. |
| `WHATSAPP_DRY_RUN` | **Render Only** | Config | Keep `true` until Meta templates and opt-in are approved. |
| `WHATSAPP_ACCESS_TOKEN` | **Render Only** | Secret | Meta Graph API permanent access token. |
| `WHATSAPP_PHONE_NUMBER_ID` | **Render Only** | Secret | Meta Phone Number ID. |
| `WHATSAPP_RECIPIENTS` | **Render Only** | Secret | E.164 phone numbers (e.g. `919876543210`). |
| `VITE_API_BASE_URL` | **Vercel Only** | Public | Your Render Backend URL, e.g. `https://techpulse-ai.onrender.com`. |

> [!CAUTION]
> **Zero Secrets in Frontend:** The Vercel frontend only receives `VITE_API_BASE_URL`. Never add `MONGODB_URI`, `OPENROUTER_API_KEY`, or `ADMIN_API_KEY` to Vercel environment variables.

---

## 7. MongoDB Atlas Network Access for Render

Render web services and cron jobs run on dynamic shared egress IP addresses.
To securely connect Render to MongoDB Atlas without exposing your database:

1. **Atlas Network Access:**
   - In MongoDB Atlas > **Network Access**, add `0.0.0.0/0` (Allow Access from Anywhere) with a clear comment: `Render Dynamic Outbound IPs`.
   - *Alternative (Static Egress):* If using Render Enterprise or an outbound proxy (QuotasGuard / Fixie), enter the dedicated static IP `/32`.
2. **Principle of Least Privilege (Database Access):**
   - In MongoDB Atlas > **Database Access**, verify your database user's privileges are scoped specifically to **Read and write to any database** or strictly to the `techpulse_ai` database.
   - Do NOT grant `atlasAdmin` cluster manager roles to the application user.
3. **Transport Security:**
   - TechPulse AI enforces TLS encryption with CA bundle verification (`tls=True`, `tlsCAFile=certifi.where()`) on all connections.

---

## 8. Rollback Procedures

### Render Web Service / Cron Jobs Rollback:
1. Open the [Render Dashboard](https://dashboard.render.com).
2. Select `techpulse-ai-backend`.
3. In the left menu, click **Deploys**.
4. Locate the last known good deploy, click the three dots (`...`), and select **Rollback to this deploy**.
5. Repeat for cron jobs if their code was modified.

### Vercel Frontend Rollback:
1. Open the [Vercel Dashboard](https://vercel.com/dashboard).
2. Select your `techpulse-ai` project.
3. Navigate to the **Deployments** tab.
4. Locate the previous working deployment, click `...`, and select **Instant Rollback**.
5. Vercel routes 100% of production traffic to the previous build in seconds without rebuilding.

---

## 9. Post-Deployment Verification Commands

Run these smoke tests against your live URLs:

```bash
# 1. Health check (must return status 200 with database connected)
curl -s https://your-backend.onrender.com/health

# 2. Check live articles
curl -s "https://your-backend.onrender.com/news?limit=3"

# 3. Check today's digest
curl -s https://your-backend.onrender.com/digest/latest

# 4. Trigger on-demand pipeline (authenticated)
curl -X POST https://your-backend.onrender.com/admin/collect \
  -H "x-admin-key: YOUR_ADMIN_KEY"
```

---

## 10. Pre-Flight Deployment Checklist

- [ ] Backend `/health` returns `"database":"connected"` and `"database_name":"techpulse_ai"`
- [ ] `/news` returns articles from Atlas
- [ ] `/docs` loads FastAPI interactive OpenAPI UI
- [ ] Frontend loads and displays live articles from Render backend
- [ ] Frontend AI Summary modal functions correctly
- [ ] Collect cron job is scheduled for `30 22 * * *` (4:00 AM IST)
- [ ] WhatsApp send cron job is scheduled for `30 0 * * *` (6:00 AM IST)
- [ ] `ADMIN_API_KEY` is set to a strong custom secret
- [ ] `WHATSAPP_DRY_RUN=true` remains active until Meta review and recipient opt-in
- [ ] `.env` is verified excluded from git tracking
- [ ] Render Blueprint (`render.yaml`) and Vercel routing (`vercel.json`) verified

