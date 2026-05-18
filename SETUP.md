# SmartSpend — Quick Start for Judges

SmartSpend is an AI-powered personal finance app: upload bank/credit statements, explore dashboards, FraudShield, EMI tracking, subscriptions, and an AI chat grounded in your real transactions.

For product overview and architecture, see [README.md](README.md).

---

## Option A — Try the live demo (fastest)

If the team has deployed the app, open the URLs from the repo [README](README.md) (fill in after deploy):

| What | URL |
|------|-----|
| **Web app** | `https://YOUR-APP.vercel.app` |
| **API health** | `https://YOUR-BACKEND.onrender.com/health` |
| **API docs (Swagger)** | `https://YOUR-BACKEND.onrender.com/docs` |

> **Note:** On Render’s free tier, the API may sleep after ~15 minutes of idle time. The first request can take **30–60 seconds**.

### Demo logins (pre-seeded)

**Password for all accounts:** `Pass@123`

| Email | Persona / use case |
|-------|-------------------|
| `judgedemo1@judge.smartspend.example.com` | Priya Kulkarni — general dashboard |
| `judgedemo2@judge.smartspend.example.com` | Rahul Mehta — **EMI / affordability demo** |
| `judgedemo3@judge.smartspend.example.com` | Ananya Desai |
| `judgedemo4@judge.smartspend.example.com` | Vikram Singh — rich transaction data |
| `judgedemo5@judge.smartspend.example.com` | Neha Joshi |
| `judgedemo6@judge.smartspend.example.com` | Karan Ahuja |

### Suggested 5-minute walkthrough

1. Sign in as **judgedemo2** (EMI flow) or **judgedemo4** (rich transaction data).
2. Open **Dashboard** — health score, income/expense KPIs, charts.
3. Open **FraudShield** — alerts, pre-payment transaction check.
4. Open **EMI Tracker** (especially on judgedemo2).
5. Open **AI chat / insights** — ask e.g. “Where did I spend the most last month?”

---

## Option B — Run locally (full setup)

### Prerequisites

| Tool | Version |
|------|---------|
| **Node.js** | LTS (18+) |
| **Python** | 3.11+ (3.13 supported) |
| **PostgreSQL** | 14+ (local install or [Neon](https://neon.tech) free cloud DB) |
| **Git** | To clone the repo |

**Optional (for full AI features):** [Groq API key](https://console.groq.com) — set as `GROQ_API_KEY`. Dashboard and fraud features work without it; AI chat/insights need at least one LLM key (Groq, OpenAI, or Gemini).

---

### Step 1 — Clone and open the project

```bash
git clone https://github.com/Cmsolanki29/smartspend-analytics.git
cd smartspend-analytics
```

---

### Step 2 — Configure environment

Copy the example env file to the **project root** (same folder as `backend/` and `frontend/`):

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

**Using local PostgreSQL:**

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=smartspend_db
DB_USER=postgres
DB_PASSWORD=your_password

JWT_SECRET_KEY=any-long-random-string-for-local-dev
GROQ_API_KEY=your_groq_key_here
```

**Using Neon (cloud PostgreSQL):**

```env
DATABASE_URL=postgresql://user:password@ep-xxx.aws.neon.tech/neondb?sslmode=require
JWT_SECRET_KEY=any-long-random-string-for-local-dev
GROQ_API_KEY=your_groq_key_here
```

Create the database once (local Postgres only):

```sql
CREATE DATABASE smartspend_db;
```

---

### Step 3 — Backend setup

```bash
cd backend
python -m venv .venv
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
pip install -U pip wheel
pip install -r requirements-base.txt -r requirements-ml-risk.txt
```

**macOS / Linux:**

```bash
source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt
```

> **Windows tip:** If `pip install -r requirements.txt` fails (long paths / torch), use `requirements-base.txt` + `requirements-ml-risk.txt` as above.

Apply database migrations and seed demo users:

```bash
python -m scripts.apply_migrations
python -m scripts.seed_judge_demo_users
```

Start the API (port **8002** — must match the frontend proxy):

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8002
```

- Verify: [http://127.0.0.1:8002/health](http://127.0.0.1:8002/health) — should show `"status": "healthy"`.
- API docs: [http://127.0.0.1:8002/docs](http://127.0.0.1:8002/docs)

---

### Step 4 — Frontend setup (new terminal)

```bash
cd frontend
npm install
npm start
```

Open **[http://localhost:3000](http://localhost:3000)**.

For local dev you usually **do not** need `REACT_APP_API_URL` — the app proxies `/api` to the backend on port **8002** automatically (`setupProxy.js`).

---

### Step 5 — Sign in or upload a statement

**A) Use demo accounts** (same as Option A) — password `Pass@123`.

**B) Create a new account** and upload a sample statement from the repo:

```
test samples/
  AXIS_BANK_ACCOUNT_STATEMENT_SAMPLE_Vikram_Singh.pdf
  AXIS_CREDIT_CARD_STATEMENT_VIKRAM_REALISTIC.pdf
  HDFC_SAMPLE_Credit_Card_Statement_Vikram_Singh.pdf
  ...
```

Supported formats: **CSV, Excel, text-based PDF** (scanned PDFs may need Tesseract OCR on the host).

---

## One-command start (Windows only)

From the repo root:

```powershell
.\start-dev.ps1
```

This kills stale processes, starts backend on **8002** and frontend on **3000** in separate windows. Wait ~30 seconds for the React app to compile, then open [http://localhost:3000](http://localhost:3000).

---

## URLs cheat sheet (local)

| Service | URL |
|---------|-----|
| Web app | http://localhost:3000 |
| API | http://127.0.0.1:8002 |
| Health check | http://127.0.0.1:8002/health |
| Swagger API docs | http://127.0.0.1:8002/docs |

---

## Troubleshooting

| Problem | What to do |
|---------|------------|
| **“Backend not reachable” on login** | Ensure uvicorn is on port **8002**. Run `.\start-dev.ps1` on Windows or restart backend manually. |
| **Database connection failed** | Check `.env` `DATABASE_URL` or `DB_*` values. For Neon, URL must include `?sslmode=require`. |
| **CORS errors (deployed app)** | On Render, set `FRONTEND_URL` to the exact Vercel URL (no trailing `/`). Redeploy backend. |
| **Slow first API call (deployed)** | Render free tier cold start — wait up to 60s or ping `/health`. |
| **AI chat empty / unavailable** | Set `GROQ_API_KEY` (or `OPENAI_API_KEY` / `GEMINI_API_KEY`) in `.env` and restart backend. |
| **pip install fails on Windows** | Use venv + `requirements-base.txt` + `requirements-ml-risk.txt` instead of full `requirements.txt`. |
| **Port already in use** | Stop old Node/Python processes or use `.\start-dev.ps1` to clean ports 3000 and 8002. |

---

## Project layout (for reference)

```
smartspend-analytics/
├── backend/          # FastAPI API, ML, migrations
├── frontend/         # React UI (Create React App)
├── test samples/     # Sample bank/card PDFs for upload demo
├── .env.example      # Copy to .env at repo root
├── render.yaml       # Backend deploy (Render)
├── README.md         # Summary, architecture, production deploy
└── SETUP.md          # This file — judge quick start
```
