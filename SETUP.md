# EXIQO Phase 2 — Local Setup Guide

> Complete instructions to run the full-stack project (Backend + Frontend + Database) on a fresh Windows machine.

---

## Prerequisites

Install these **before** starting:

| Tool | Version | Download |
|------|---------|----------|
| Python | 3.11 or 3.13 | https://python.org/downloads |
| Node.js | 18+ (LTS) | https://nodejs.org |
| PostgreSQL | 15+ | https://www.postgresql.org/download/windows |
| Git (optional) | any | https://git-scm.com |

> During PostgreSQL install, set password for the `postgres` user. You will need it in Step 2.

---

## Step 1 — Unzip and Open Project

Unzip the project and open a **PowerShell** terminal inside the project root folder:

```
exiqo-phase-2/
├── backend/
├── frontend/
├── database/
├── .env
├── start-backend.ps1
└── start-frontend.ps1
```

---

## Step 2 — Configure Environment Variables

Open the `.env` file in the project root and fill in your values:

```env
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=smartspend_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password_here    ← change this

JWT_SECRET_KEY=any_long_random_string_here ← change this (e.g. paste 40 random chars)

GROQ_API_KEY=your_groq_api_key_here        ← get free key at console.groq.com

CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001

ADMIN_TOKEN=dev-admin-secret
PHASE_9_AGENT_ENABLED=true
```

Also open `frontend/.env.local` — **you can leave `REACT_APP_API_URL` unset** in development. The app calls same-origin `/api`, and Create React App proxies that to `http://127.0.0.1:8001` (see `frontend/package.json` → `"proxy"`). That avoids CORS and avoids a wrong port (e.g. 8012) when the backend is on **8001**.

Optional (production builds only): set `REACT_APP_API_URL` at build time if the API is not co-hosted.

```env
# (optional in dev) REACT_APP_API_URL=https://your-api.example.com/api
```

---

## Step 3 — Create the Database

Open **pgAdmin** or **psql** and run:

```sql
CREATE DATABASE smartspend_db;
```

Then run the schema files in order. From the project root in PowerShell:

```powershell
psql -U postgres -d smartspend_db -f database/schema.sql
psql -U postgres -d smartspend_db -f database/fraud_schema.sql
psql -U postgres -d smartspend_db -f database/festival_purchase_schema.sql
psql -U postgres -d smartspend_db -f database/schema_additions.sql
```

> If `psql` is not in PATH, find it at: `C:\Program Files\PostgreSQL\15\bin\psql.exe`

---

## Step 4 — Install Backend Dependencies

Open a **new PowerShell terminal** in the project root:

```powershell
cd backend
pip install -r requirements.txt
```

> First install takes 3–5 minutes (PyTorch, XGBoost, etc.)

---

## Step 5 — Start the Backend

From the **project root** folder:

```powershell
.\start-backend.ps1
```

This starts the FastAPI server on **http://localhost:8001**

To verify it's running, open in browser:
- http://localhost:8001/health → should show `{"status":"healthy"}`
- http://localhost:8001/docs → interactive API docs

> Keep this terminal open. Backend must stay running.

---

## Step 6 — Install Frontend Dependencies

Open a **second PowerShell terminal** in the project root:

```powershell
cd frontend
npm install
```

> First install takes 2–3 minutes.

---

## Step 7 — Start the Frontend

From the project root (recommended — **always port 3000**, frees the port, clears a bad `REACT_APP_API_URL` from your shell):

```powershell
.\start-frontend.ps1
```

This starts **http://localhost:3000**. The app talks to the API via same-origin **`/api`**, which Create React App **proxies** to **http://127.0.0.1:8001** (see `frontend/package.json` → `"proxy"`). You do **not** need `REACT_APP_API_URL` in dev. The browser may open automatically; you should see the **SmartSpend intro animation**.

If you insist on `cd frontend` + `npm start` by hand, keep **`PORT=3000`** in `frontend/.env.local` and never point `REACT_APP_API_URL` at a random localhost port.

---

## Step 8 — Create Your Account

1. Watch the intro animation (or click **SKIP**)
2. Click **Create an account**
3. Sign up with your name, email, password
4. Complete bank linking (select any demo bank)
5. You're in — the full dashboard will load

---

## Quick Start (after first setup)

Once everything is installed, just run these two scripts each time:

**Terminal 1 — Backend:**
```powershell
.\start-backend.ps1
```

**Terminal 2 — Frontend:**
```powershell
.\start-frontend.ps1
```

Then open → http://localhost:3000

---

## Troubleshooting

### `psql: command not found`
Add PostgreSQL bin to PATH:
```
C:\Program Files\PostgreSQL\15\bin
```
Or use full path: `& "C:\Program Files\PostgreSQL\15\bin\psql.exe"`

### Backend starts but shows DB error
- Check `DB_PASSWORD` in `.env` matches your PostgreSQL password
- Make sure PostgreSQL service is running (search "Services" in Windows → find PostgreSQL → Start)

### Frontend shows blank page or API errors
- Make sure backend is running on port **8001** first (`.\start-backend.ps1`).
- In **development**, do **not** set `REACT_APP_API_URL` to another localhost port unless the API really runs there; the UI uses `/api` → CRA **proxy** → `127.0.0.1:8001`.
- Open browser DevTools (F12) → Console / Network → check for failed `/api/...` calls.

### Port 8001 already in use
The `start-backend.ps1` script auto-kills any old process on port 8001. Just run it again.

### `torch` / `torch_geometric` install fails
These are optional for Phase 10/11 features. The app works without them:
```powershell
pip install -r requirements.txt --ignore-requires-python
```
Or skip torch manually if needed — core features (Fraud Shield, Dashboard, EMI, etc.) don't need it.

---

## Project Ports Summary

| Service | Port | URL |
|---------|------|-----|
| Frontend (React) | 3000 | http://localhost:3000 |
| Backend (FastAPI) | 8001 | http://localhost:8001 |
| PostgreSQL | 5432 | (internal) |
| API Docs | 8001 | http://localhost:8001/docs |

---

## Tech Stack

- **Frontend:** React 18, Tailwind CSS, Framer Motion, Recharts
- **Backend:** FastAPI, Python 3.13, Uvicorn
- **Database:** PostgreSQL 15
- **AI/ML:** XGBoost, PyTorch GNN, Groq LLaMA (Phase 9-12)
- **Auth:** JWT (7-day access token, 30-day refresh)
