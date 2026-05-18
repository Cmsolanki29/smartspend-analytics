# SmartSpend Analytics

> **Your money, intelligently shielded.** — An AI-native personal finance OS that turns bank and credit-card statements into a unified command center for visibility, fraud protection, savings, and planning.

**Hackathon:** EXIQO Code-AI-Thon · **Repo:** [smartspend-analytics](https://github.com/Cmsolanki29/smartspend-analytics) · **Judge setup:** [SETUP.md](SETUP.md)

| | URL |
|---|-----|
| **Live app** | _Set after Vercel deploy — e.g. `https://smartspend-analytics.vercel.app`_ |
| **API / Swagger** | _Set after Render deploy — e.g. `https://smartspend-backend.onrender.com/docs`_ |
| **Health check** | `GET /health` on your backend URL |

---

## Summary

SmartSpend is an end-to-end **personal finance platform** for consumers who manage money across bank accounts, credit cards, UPI, subscriptions, and EMIs. Users connect data by uploading statements (CSV, Excel, or text PDF) or using pre-seeded demo accounts. The app then delivers:

| Pillar | What it does |
|--------|----------------|
| **See** | Dashboard KPIs, health score (0–100), spending charts, searchable transactions |
| **Protect** | **FraudShield** — 12-phase risk stack (rules, Isolation Forest, XGBoost, graph/GNN, LLM investigation, pre-payment checker) |
| **Save** | Subscription Intelligence (KEEP/REVIEW/CANCEL verdicts), dark-pattern detector (₹1 traps, zombies, duplicates) |
| **Plan** | EMI tracker, festival budgets, purchase goals, AI trip planner |
| **Ask** | Context-grounded AI chat and insights — answers use **your** ledger, not generic finance tips |

Unlike a simple expense tracker, every module feeds a central **Financial State Engine** that recalculates monthly surplus and pushes alerts when the user is overcommitted.

**Tech stack:** React 18 · FastAPI · PostgreSQL (Neon) · scikit-learn / XGBoost · Groq / OpenAI / Gemini · Deploy on **Vercel** (UI) + **Render** (API) + **Neon** (DB).

---

## Quick start for judges

> **Full step-by-step guide:** [SETUP.md](SETUP.md) (live demo, local install, troubleshooting)

### Option A — Live demo (fastest)

1. Open the deployed web app URL (see table above).
2. Sign in with a demo account — **password for all:** `Pass@123`

| Email | Persona |
|-------|---------|
| `judgedemo1@judge.smartspend.example.com` | Priya Kulkarni — general dashboard |
| `judgedemo2@judge.smartspend.example.com` | Rahul Mehta — **EMI / affordability demo** |
| `judgedemo3@judge.smartspend.example.com` | Ananya Desai |
| `judgedemo4@judge.smartspend.example.com` | Vikram Singh — rich transaction data |
| `judgedemo5@judge.smartspend.example.com` | Neha Joshi |
| `judgedemo6@judge.smartspend.example.com` | Karan Ahuja |

3. Suggested walkthrough: **Dashboard** → **FraudShield** → **EMI Tracker** (judgedemo2) → **AI chat** (“Where did I spend the most last month?”).

> **Note:** Render free tier sleeps after ~15 min idle; first API call may take **30–60 seconds**.

### Option B — Run locally

**Prerequisites:** Node.js 18+, Python 3.11+, PostgreSQL 14+ (or [Neon](https://neon.tech) cloud DB), optional [Groq API key](https://console.groq.com) for AI features.

```bash
# 1. Clone
git clone https://github.com/Cmsolanki29/smartspend-analytics.git
cd smartspend-analytics

# 2. Environment (repo root)
cp .env.example .env
# Edit .env — set DATABASE_URL or DB_* and GROQ_API_KEY

# 3. Backend
cd backend
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1
# macOS/Linux:  source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements-base.txt -r requirements-ml-risk.txt   # or requirements.txt
python -m scripts.apply_migrations
python -m scripts.seed_judge_demo_users
uvicorn main:app --reload --host 127.0.0.1 --port 8002

# 4. Frontend (new terminal)
cd frontend
npm install
npm start
```

| Service | URL |
|---------|-----|
| Web app | http://localhost:3000 |
| API | http://127.0.0.1:8002 |
| Swagger docs | http://127.0.0.1:8002/docs |
| Health | http://127.0.0.1:8002/health |

**Windows one-command start** (from repo root):

```powershell
.\start-dev.ps1
```

Kills stale processes, starts backend on **8002** and frontend on **3000**. Wait ~30s for React to compile.

**Sample statements** for upload demos live in `test samples/` (Axis, HDFC PDFs).

---

## Production deployment

### 1. Database — [Neon](https://neon.tech)

```bash
cd backend
pip install -r requirements-render.txt
# Windows CMD:  set DATABASE_URL=postgresql://...
# macOS/Linux:  export DATABASE_URL=postgresql://...
python -m scripts.deploy_production_db
```

Applies migrations and seeds the six judge demo users.

### 2. Backend — [Render](https://render.com)

1. Push repo to GitHub → Render → **New Blueprint** → connect repo (`render.yaml`).
2. Set secrets: `DATABASE_URL`, `GROQ_API_KEY`, `FRONTEND_URL` (Vercel URL, no trailing slash).
3. Verify: `curl https://YOUR-BACKEND.onrender.com/health`

### 3. Frontend — [Vercel](https://vercel.com)

1. Import repo → **Root Directory:** `frontend`
2. Env: `REACT_APP_API_URL=https://YOUR-BACKEND.onrender.com/api`
3. Set `FRONTEND_URL` on Render to the Vercel URL → redeploy backend (CORS).

---

## Architecture

### System overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     React SPA (Vercel / :3000)                   │
│  Intro · Auth · Dashboard · FraudShield · Planning · AI Chat    │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST /api  (+ SSE for chat/insights)
                             │ WebSocket (realtime fraud feed)
┌────────────────────────────▼────────────────────────────────────┐
│                  FastAPI Backend (Render / :8002)                │
│  routes/          HTTP layer, JWT auth, user-scoped APIs         │
│  services/        Business logic, ML, LLM, parsers               │
│  workers/         Redis consumers (alerts, drift, retrain)       │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        PostgreSQL        Redis         LLM APIs
        (Neon)         (optional)    Groq → OpenAI → Gemini
```

**Data → AI pipeline** (balances are never hallucinated):

```
PostgreSQL (transactions, EMI, goals, festivals)
        │
        ▼
ai_context_service  — compress ledger into context packet
        │
        ├──► Deterministic engines (health score, surplus, subscription verdicts)
        └──► LLM routes (insights, chat, investigation) — structured prompts only
```

---

### Backend modules

| Module | Path | Responsibility |
|--------|------|----------------|
| **Auth & onboarding** | `routes/auth.py`, `otp.py`, `onboarding.py` | JWT sign-up/sign-in, OTP, source selection |
| **Documents & upload** | `routes/documents.py`, `services/upload_pipeline.py` | PDF/CSV/Excel ingestion, bank parsers (Axis, HDFC, …) |
| **Dashboard & analytics** | `routes/dashboard.py`, `financial_summary.py`, `analysis.py` | Scoped KPIs (bank / card / merged), trends, categories |
| **Transactions** | `routes/transactions.py`, `user_scoped_api.py` | Ledger, search, risk badges |
| **Health score** | `routes/health_score.py`, `services/scorer.py` | 0–100 score from savings, stability, anomalies, subscriptions |
| **Financial state** | `routes/financial_state.py`, `services/` state engine | Monthly surplus, RED/YELLOW alerts after mutations |
| **Anomalies (ML)** | `routes/anomaly.py`, `services/ml_model.py` | Per-user Isolation Forest on transaction features |
| **FraudShield** | `routes/fraud_shield.py`, `services/risk_*` | 12-phase pipeline: rules, XGBoost, graph, SHAP, LLM agent, orchestrator |
| **Investigations** | `routes/investigations.py`, `explainability.py` | Analyst console, factor explanations |
| **AI chat & insights** | `routes/ai_chat.py`, `insights.py`, `ai_context_service.py` | SSE streaming chat, insights waterfall, jailbreak guard |
| **Dark patterns** | `routes/dark_patterns.py` | ₹1 traps, zombies, duplicates, price hikes |
| **Subscriptions** | `routes/subscription_intelligence.py`, `subscription_graveyard.py` | Verdict engine, device-link signals, graveyard |
| **EMI** | `routes/emi_detector.py`, `emi_affordability_check.py` | Recurring detection, trap detector, affordability |
| **Festival planner** | `routes/festival_predictor.py`, `festival_planner_ext.py` | Indian festival calendar, budget vs surplus |
| **Purchase planner** | `routes/purchase_planner.py` | Goal-first buys, sacrifice analysis |
| **Trip planner** | `routes/trip_planner.py` | Agent + MCP travel tools |
| **Realtime** | `routes/realtime_ws.py` | Live fraud / transaction feed |
| **Admin & MLOps** | `routes/admin.py`, `workers/*` | Diagnostics, drift monitor, retrain scheduler |
| **Database** | `database/migrations/`, `scripts/apply_migrations.py` | Versioned SQL schema (36+ migrations) |

**FraudShield phases (high level):**

| Phase | Capability |
|-------|------------|
| 1–4 | Event engine, feature store, supervised scoring, decision engine |
| 5–8 | MLOps registry, graph intelligence, SHAP explainability, feedback flywheel |
| 9–12 | LLM investigation agent, GNN (optional), DNN shadow, orchestrator |

Phase flags are controlled via `.env` (`PHASE_9_AGENT_ENABLED`, `PHASE_12_ORCHESTRATOR_ENABLED`, etc.).

---

### Frontend sections

| UI area | Location | Maps to |
|---------|----------|---------|
| **Intro & auth** | `components/intro/`, `context/AuthContext.tsx` | Cinematic onboarding, sign-up/in |
| **Source selection** | `pages/Onboarding/SourceSelection` | Bank-only / card-only / merged dashboard mode |
| **Dashboard** | `components/Dashboard/` | KPIs, health gauge, charts, AI command center |
| **Transactions** | `components/app-tabs/TransactionsTab` | Searchable ledger with anomaly badges |
| **Insights** | `components/app-tabs/InsightsTab` | LLM-generated spending narratives |
| **FraudShield** | `components/FraudShield/` | Alerts, pre-pay checker, behavior profile, Chain Vault |
| **CyberSafe** | `pages/RiskAwareness/` | Scam education, connect flow |
| **Dark patterns** | `components/DarkPatterns/` | Trap and duplicate charge analysis |
| **Subscriptions** | `pages/SubscriptionHub`, `SubscriptionConnect` | Device link, verdict hub, reminders |
| **EMI** | `components/EMI/` | Tracker, calculator, trap detector |
| **Festival / Purchase** | `components/Festival/`, `components/Purchase/` | Budget planning with AI advice |
| **Trip planner** | `pages/AIActions/TripPlannerPage` | Agentic travel planning |
| **AI chat** | `pages/AIAnalysisEngine` | Streaming chat with statement upload |
| **Admin** | `pages/admin/AdminDiagnostics` | Internal diagnostics (token-gated) |

**API client:** `frontend/src/services/api.js` — dev proxy via `setupProxy.js` → backend port **8002**.

---

## Project structure

```
exiqo/
├── backend/
│   ├── main.py                 # FastAPI app entry
│   ├── routes/                 # HTTP endpoints by domain
│   ├── services/               # ML, LLM, parsers, business logic
│   ├── workers/                # Redis-backed async jobs (risk engine)
│   ├── database/migrations/    # SQL migrations
│   └── scripts/                # apply_migrations, seed_judge_demo_users, deploy_production_db
├── frontend/
│   ├── src/components/         # UI by feature (Dashboard, FraudShield, EMI, …)
│   ├── src/pages/              # Full-page views (subscriptions, trip planner, admin)
│   ├── src/services/           # Axios API clients
│   └── setupProxy.js           # Dev proxy → :8002
├── test samples/               # Sample bank/card PDFs for demos
├── render.yaml                 # Render Blueprint (backend)
├── .env.example                # Copy to .env at repo root
├── start-dev.ps1               # Windows: clean restart backend + frontend
└── SMARTSPEND_PROJECT_OVERVIEW.md   # Extended product & pitch reference
```

---

## Environment variables

Copy `.env.example` → `.env` at the **repo root**.

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` or `DB_*` | PostgreSQL connection |
| `JWT_SECRET_KEY` | Auth token signing |
| `GROQ_API_KEY` | Primary LLM (chat, insights, planning) |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | Optional fallbacks in insights waterfall |
| `FRONTEND_URL` | CORS origin for production |
| `REACT_APP_API_URL` | Frontend build only (Vercel) — must end with `/api` |

---

## API highlights

| Endpoint | Description |
|----------|-------------|
| `GET /health` | DB + dependency status |
| `POST /api/auth/signin` | JWT login |
| `POST /api/documents/upload` | Statement ingestion |
| `GET /api/dashboard/{user_id}` | Scoped KPIs |
| `POST /api/fraud-shield/{user_id}/check-transaction` | Live pre-payment fraud check |
| `POST /api/ai-chat/{user_id}/stream` | Streaming AI chat (SSE) |

Full interactive docs: `/docs` on your backend URL.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Backend not reachable on login | Run API on port **8002**; use `.\start-dev.ps1` on Windows |
| CORS error (deployed) | `FRONTEND_URL` must exactly match Vercel URL (no trailing `/`) |
| Slow first load (deployed) | Render cold start — wait up to 60s or ping `/health` |
| DB connection failed | Neon URL needs `?sslmode=require` |
| AI chat unavailable | Set `GROQ_API_KEY` in `.env` and restart backend |
| pip install fails (Windows) | Use venv + `requirements-base.txt` + `requirements-ml-risk.txt` |
| Empty PDF parse | Use CSV/Excel or text-based PDF; scanned PDFs need Tesseract |

---

## License

MIT — replace with your team’s license and acknowledgements as needed.
