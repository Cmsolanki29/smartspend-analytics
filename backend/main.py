"""SmartSpend Analytics API — Phase 2 FastAPI application."""
# reload-bump: source-badge-v3

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Load `.env` before any other local imports read os.environ (API keys, DB, etc.).
# Use override=True so empty/missing keys in the shell do not mask values from the file.
_env_loaded = False
for _env_path in (
    Path(r"C:\Users\Chirag\Downloads\SMARTSPENDAPP\exiqo\.env"),  # absolute — most reliable on Windows
    Path(__file__).resolve().parent.parent / ".env",  # repo root (exiqo/.env)
    Path(__file__).resolve().parent / ".env",  # backend/.env
    Path.cwd() / ".env",
    Path.cwd().parent / ".env",
):
    try:
        if _env_path.is_file():
            load_dotenv(_env_path, override=True)
            print(f"[smartspend] Loaded .env from {_env_path}", flush=True)
            _env_loaded = True
            break
    except OSError:
        continue
if not _env_loaded:
    load_dotenv(override=True)
    print("[smartspend] No .env file in known paths; using load_dotenv() discovery + existing env", flush=True)

import os as _os
print(f"[smartspend] OPENAI_API_KEY: {'SET (len=' + str(len(_os.getenv('OPENAI_API_KEY', ''))) + ')' if _os.getenv('OPENAI_API_KEY') else '*** MISSING ***'}", flush=True)
print(f"[smartspend] GROQ_API_KEY:   {'SET (len=' + str(len(_os.getenv('GROQ_API_KEY', ''))) + ')' if _os.getenv('GROQ_API_KEY') else '*** MISSING ***'}", flush=True)

import asyncio
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db import get_db, test_db_connection
from models.schemas import (
    AnomalyResponse,
    DashboardSummary,
    HealthScoreResponse,
    MonthlyTrend,
    SpendingAnalysis,
    UserResponse,
)
from routes import (
    ai_chat,
    analysis,
    anomaly,
    auth,
    dark_patterns,
    dashboard,
    documents,
    emi_affordability_check,
    emi_detector,
    festival_important_days,
    festival_predictor,
    financial_state,
    fraud_shield,
    health_score,
    insights,
    onboarding,
    otp,
    pattern_alerts,
    purchase_planner,
    subscription_graveyard,
    subscription_intelligence,
    transactions,
)
from services.ml_model import ml_detector
from services.scorer import calculate_health_score

# ── Phase 1-8 Risk Engine imports (Chirag Solanki) ──────────────────────────
try:
    from routes import admin as _admin_rt
    from routes import explainability as _explain_rt
    from routes import feedback as _feedback_rt
    from routes import risk_profile as _risk_profile_rt
    from routes import investigations as _investigations_rt
    from routes import gnn as _gnn_rt
    from routes import dnn as _dnn_rt
    from routes import orchestrator as _orchestrator_rt
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from core.db import init_pool, close_pool
    from core.redis import init_redis, close_redis
    from workers.retrain_feed_consumer import retrain_feed_consumer
    from workers.review_queue_worker import run_assignment_cycle
    _RISK_ENGINE_OK = True
except Exception as _risk_err:
    _RISK_ENGINE_OK = False
    print(f"[RiskEngine] Skipping Phase 1-8 imports: {_risk_err}")
_risk_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Do not block HTTP readiness on ML training. train_all_users() can take minutes
    with large seeded DBs; the frontend axios timeout (15s) would fail signup/signin
    if we ran it synchronously before the first yield.
    """

    async def _warm_ml_models() -> None:
        try:
            await asyncio.to_thread(ml_detector.train_all_users)
            print("SmartSpend ML models warmed up.")
        except Exception as exc:  # noqa: BLE001
            print(f"Startup ML/DB step warning: {exc}")

    print("SmartSpend Backend Ready (ML training running in background).")

    import sys

    try:
        import pdfplumber as _pp

        print(
            f"[documents] pdfplumber OK (v{getattr(_pp, '__version__', '?')}) — PDF statement extraction enabled."
        )
    except Exception as _pdf_exc:  # noqa: BLE001
        print(
            f"[documents] WARNING: pdfplumber not usable ({type(_pdf_exc).__name__}: {_pdf_exc}). "
            f"Install into the SAME Python that runs uvicorn:\n"
            f"  {sys.executable} -m pip install pdfplumber"
        )

    asyncio.create_task(_warm_ml_models())

    # ── Phase 1-8 startup ──────────────────────────────────────────────────
    if _RISK_ENGINE_OK:
        try:
            await init_pool()
            await init_redis()
        except Exception as _e:
            print(f"[RiskEngine] Pool/Redis init skipped: {_e}")
        try:
            global _risk_scheduler
            _risk_scheduler = AsyncIOScheduler(timezone="UTC")
            _risk_scheduler.add_job(
                run_assignment_cycle, "interval", minutes=5,
                id="review_queue_worker", replace_existing=True,
            )
            _risk_scheduler.start()
        except Exception as _e:
            print(f"[RiskEngine] Scheduler skipped: {_e}")
        try:
            asyncio.create_task(retrain_feed_consumer.start())
        except Exception as _e:
            print(f"[RiskEngine] Background tasks skipped: {_e}")

    if os.getenv("PATTERN_ALERT_CRON", "0") == "1":
        async def _pattern_alert_loop() -> None:
            from db import get_connection
            from services.pattern_predictor import (
                expire_stale_alerts,
                predict_upcoming_charges,
                upsert_pattern_alerts,
            )

            await asyncio.sleep(120)
            while True:
                try:

                    def _scan_once() -> None:
                        cnx = get_connection()
                        try:
                            expire_stale_alerts(cnx)
                            cur = cnx.cursor()
                            cur.execute("SELECT id FROM users")
                            uids = [r[0] for r in cur.fetchall()]
                            cur.close()
                            for uid in uids:
                                pr = predict_upcoming_charges(cnx, uid)
                                upsert_pattern_alerts(cnx, pr)
                            cnx.commit()
                        except Exception as exc:
                            cnx.rollback()
                            print(f"[pattern-alerts] scan error: {exc}")
                        finally:
                            cnx.close()

                    await asyncio.to_thread(_scan_once)
                except Exception as exc:
                    print(f"[pattern-alerts] loop: {exc}")
                await asyncio.sleep(6 * 3600)

        asyncio.create_task(_pattern_alert_loop())
        print("Pattern alert cron enabled (PATTERN_ALERT_CRON=1, every 6h).")

    yield

    # ── Phase 1-8 shutdown ─────────────────────────────────────────────────
    if _RISK_ENGINE_OK:
        try:
            if _risk_scheduler and _risk_scheduler.running:
                _risk_scheduler.shutdown(wait=False)
            await close_redis()
            await close_pool()
        except Exception as _e:
            print(f"[RiskEngine] Shutdown warning: {_e}")


app = FastAPI(
    title="SmartSpend Analytics API",
    version="2.0.0",
    lifespan=lifespan,
)

_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:3001,http://127.0.0.1:3001,"
    "http://localhost:3005,http://127.0.0.1:3005",
).strip()
_allow_origins = [o.strip() for o in _origins.split(",") if o.strip()] or [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler — never let an unhandled exception crash the server silently."""
    import traceback
    print(f"[GlobalError] {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}. Check backend logs."},
    )

app.include_router(ai_chat.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(onboarding.router, prefix="/api")
app.include_router(otp.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(anomaly.router, prefix="/api")
app.include_router(health_score.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(emi_detector.router, prefix="/api")
app.include_router(emi_affordability_check.router, prefix="/api")
app.include_router(subscription_graveyard.router, prefix="/api")
app.include_router(subscription_intelligence.router, prefix="/api")
app.include_router(dark_patterns.router, prefix="/api")
app.include_router(fraud_shield.router, prefix="/api")
app.include_router(festival_important_days.router, prefix="/api")
app.include_router(festival_predictor.router, prefix="/api")
app.include_router(purchase_planner.router, prefix="/api")
app.include_router(financial_state.router, prefix="/api")
app.include_router(pattern_alerts.router, prefix="/api")
app.include_router(documents.router, prefix="/api")

# ── Phase 1-8 routers ──────────────────────────────────────────────────────
if _RISK_ENGINE_OK:
    try:
        app.include_router(_admin_rt.router, prefix="/api")
        app.include_router(_explain_rt.router, prefix="/api")
        app.include_router(_feedback_rt.router, prefix="/api")
        app.include_router(_risk_profile_rt.router, prefix="/api")
        app.include_router(_investigations_rt.router, prefix="/api")
        app.include_router(_gnn_rt.router, prefix="/api")
        app.include_router(_dnn_rt.router, prefix="/api")
        app.include_router(_orchestrator_rt.router, prefix="/api")
    except Exception as _e:
        print(f"[RiskEngine] Router registration skipped: {_e}")


@app.get("/api")
def api_root() -> dict[str, Any]:
    """So `GET /api` is not a bare 404 when checking the API base in a browser."""
    return {
        "name": "SmartSpend Analytics API",
        "api_base": "/api",
        "docs": "/docs",
        "health": "/health",
        "auth": {"signup": "POST /api/auth/signup", "signin": "POST /api/auth/signin", "me": "GET /api/auth/me"},
        "onboarding": {
            "banks": "GET /api/onboarding/available-banks",
            "link": "POST /api/onboarding/link-bank",
            "status": "GET /api/onboarding/status",
        },
        "otp": {"send": "POST /api/otp/send", "verify": "POST /api/otp/verify"},
    }


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "SmartSpend Analytics API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": [
            "GET /api",
            "POST /api/auth/signup",
            "POST /api/auth/signin",
            "POST /api/auth/refresh",
            "POST /api/auth/logout",
            "GET /api/auth/me",
            "GET /api/auth/verify",
            "GET /api/onboarding/available-banks",
            "GET /api/onboarding/status",
            "POST /api/onboarding/link-bank",
            "POST /api/otp/send",
            "POST /api/otp/verify",
            "GET /api/users",
            "GET /api/users/{user_id}",
            "GET /api/transactions/{user_id}",
            "GET /api/transactions/{user_id}/summary",
            "POST /api/transactions/{user_id}/upload",
            "GET /api/analysis/{user_id}/spending",
            "GET /api/analysis/{user_id}/trends",
            "GET /api/analysis/{user_id}/merchants",
            "GET /api/analysis/{user_id}/simulate",
            "GET /api/anomalies/{user_id}",
            "POST /api/anomalies/{user_id}/run-detection",
            "GET /api/anomalies/{user_id}/stats",
            "GET /api/anomalies/{user_id}/patterns",
            "GET /api/anomalies/{user_id}/alerts",
            "GET /api/health-score/{user_id}",
            "GET /api/health-score/{user_id}/history",
            "GET /api/insights/{user_id}",
            "GET /api/insights/{user_id}/quick-summary",
            "GET /api/insights/{user_id}/health-narrative",
            "GET /api/insights/{user_id}/anomaly/{transaction_id}",
            "POST /api/insights/{user_id}/simulate",
            "GET /api/emi/{user_id}",
            "POST /api/emi/{user_id}/affordability-check",
            "POST /api/emi/{user_id}/affordability",
            "POST /api/emi/{user_id}/calculate-impact",
            "POST /api/emi/{user_id}/scan",
            "GET /api/subscriptions/{user_id}",
            "GET /api/dark-patterns/{user_id}",
            "GET /api/dark-patterns/{user_id}/rupee-traps",
            "POST /api/dark-patterns/{user_id}/scan",
            "POST /api/dark-patterns/{user_id}/{pattern_id}/resolve",
            "GET /api/fraud-shield/summary",
            "GET /api/fraud-shield/patterns",
            "GET /api/fraud-shield/{user_id}/analyze",
            "POST /api/fraud-shield/{user_id}/check-transaction",
            "GET /api/fraud-shield/{user_id}/alerts",
            "POST /api/fraud-shield/{user_id}/alerts/{alert_id}/action",
            "GET /api/fraud-shield/{user_id}/stats",
            "GET /api/festivals/{user_id}",
            "GET /api/festivals/{user_id}/history",
            "GET /api/festivals/{user_id}/important-days",
            "POST /api/festivals/{user_id}/important-days",
            "PUT /api/festivals/{user_id}/important-days/{event_id}",
            "DELETE /api/festivals/{user_id}/important-days/{event_id}",
            "POST /api/festivals/{user_id}/set-budget",
            "GET /api/purchases/{user_id}",
            "POST /api/purchases/{user_id}/add-goal",
            "POST /api/purchases/{user_id}/{goal_id}/postpone",
            "POST /api/purchases/{user_id}/goals/{goal_id}/postpone",
            "PUT /api/purchases/{user_id}/{goal_id}/update-savings",
            "DELETE /api/purchases/{user_id}/{goal_id}",
            "GET /api/dashboard/{user_id}",
            "GET /api/ml/status",
        ],
    }


@app.get("/api/ml/status")
def ml_status() -> dict[str, Any]:
    return {
        "models_trained": sorted(ml_detector.models.keys()),
        "users_covered": len(ml_detector.models),
        "status": "ready" if ml_detector.models else "not_trained",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    import sys

    ok = test_db_connection()
    pdf: dict[str, Any] = {"ok": False, "version": None, "error": None}
    try:
        import pdfplumber as _pp_health

        pdf = {
            "ok": True,
            "version": getattr(_pp_health, "__version__", None),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        pdf = {"ok": False, "version": None, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "status": "healthy" if ok else "degraded",
        "db": "connected" if ok else "disconnected",
        "ml": "ready",
        "version": "2.0.0",
        "python_executable": sys.executable,
        "pdfplumber": pdf,
    }


# ── Phase 9-12 individual health probes ────────────────────────────────────
import time as _time


@app.get("/api/health/llm-investigator")
def health_llm_investigator() -> dict[str, Any]:
    """Probe Phase 9 LLM investigator — checks Groq API reachability."""
    t0 = _time.perf_counter()
    try:
        from services.ai_service import call_groq
        result = call_groq(
            "You are a health-check probe.",
            "Reply with exactly the word: ok",
            max_tokens=4,
            temperature=0,
        )
        latency = int((_time.perf_counter() - t0) * 1000)
        if result and "ok" in str(result).lower():
            return {"status": "ok", "latency_ms": latency, "phase": 9}
        return {"status": "degraded", "latency_ms": latency, "phase": 9}
    except Exception as e:
        latency = int((_time.perf_counter() - t0) * 1000)
        return {"status": "offline", "latency_ms": latency, "phase": 9, "error": str(e)[:80]}


@app.get("/api/health/gnn")
def health_gnn() -> dict[str, Any]:
    """Probe Phase 10 GNN — checks if model file and embedding store are ready."""
    t0 = _time.perf_counter()
    try:
        from core.config import get_settings
        s = get_settings()
        import os
        model_path = os.path.join("models", "gnn_model.pt")
        loaded = os.path.exists(model_path)

        # Also probe the inference module to confirm embeddings store
        try:
            from services.phase_10_gnn.inference import get_status
            status = get_status()
            loaded = loaded or bool(status.get("embeddings") or status.get("model_loaded"))
        except Exception:
            pass

        latency = int((_time.perf_counter() - t0) * 1000)
        enabled = bool(s.PHASE_10_GNN_ENABLED)
        return {
            "status": "ok" if (enabled and loaded) else ("degraded" if enabled else "offline"),
            "latency_ms": latency,
            "enabled": enabled,
            "model_loaded": loaded,
            "phase": 10,
        }
    except Exception as e:
        latency = int((_time.perf_counter() - t0) * 1000)
        return {"status": "offline", "latency_ms": latency, "phase": 10, "error": str(e)[:80]}


@app.get("/api/health/dnn")
def health_dnn() -> dict[str, Any]:
    """Probe Phase 11 DNN — checks if DNN model file is loaded."""
    t0 = _time.perf_counter()
    try:
        from core.config import get_settings
        s = get_settings()
        import os
        model_path = os.path.join("models", "dnn_model.pt")
        loaded = os.path.exists(model_path)

        try:
            from services.phase_11_dnn.inference import get_dnn_status
            status = get_dnn_status()
            loaded = loaded or bool(status.get("model_loaded"))
        except Exception:
            pass

        latency = int((_time.perf_counter() - t0) * 1000)
        enabled = bool(s.PHASE_11_DNN_ENABLED)
        return {
            "status": "ok" if (enabled and loaded) else ("degraded" if enabled else "offline"),
            "latency_ms": latency,
            "enabled": enabled,
            "model_loaded": loaded,
            "phase": 11,
        }
    except Exception as e:
        latency = int((_time.perf_counter() - t0) * 1000)
        return {"status": "offline", "latency_ms": latency, "phase": 11, "error": str(e)[:80]}


@app.get("/api/health/orchestrator")
def health_orchestrator() -> dict[str, Any]:
    """Probe Phase 12 Orchestrator — checks routing table is initialized."""
    t0 = _time.perf_counter()
    try:
        from core.config import get_settings
        s = get_settings()
        enabled = bool(s.PHASE_12_ORCHESTRATOR_ENABLED)
        # The routing policy module only needs config — no file on disk required
        from services.phase_12_orchestrator.routing_policy import route
        latency = int((_time.perf_counter() - t0) * 1000)
        return {
            "status": "ok" if enabled else "offline",
            "latency_ms": latency,
            "enabled": enabled,
            "routing_table": "initialized",
            "phase": 12,
        }
    except Exception as e:
        latency = int((_time.perf_counter() - t0) * 1000)
        return {"status": "offline", "latency_ms": latency, "phase": 12, "error": str(e)[:80]}


@app.get("/api/users", response_model=list[UserResponse])
def list_users(conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, name, email, monthly_income::float, savings_goal::float, risk_tolerance
            FROM users ORDER BY id;
            """
        )
        return [
            UserResponse(
                id=r[0],
                name=r[1],
                email=r[2],
                monthly_income=float(r[3]),
                savings_goal=float(r[4]),
                risk_tolerance=r[5],
            )
            for r in cur.fetchall()
        ]
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()


@app.get("/api/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, name, email, monthly_income::float, savings_goal::float, risk_tolerance
            FROM users WHERE id = %s;
            """,
            (user_id,),
        )
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "User not found")
        return UserResponse(
            id=r[0],
            name=r[1],
            email=r[2],
            monthly_income=float(r[3]),
            savings_goal=float(r[4]),
            risk_tolerance=r[5],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()


@app.get("/api/dashboard/{user_id}", response_model=DashboardSummary)
def dashboard(user_id: int, conn=Depends(get_db)):
    today = date.today()
    m, y = today.month, today.year
    cur = conn.cursor()
    try:
        # User row + last_login (used as a freshness fallback when no bank is linked).
        cur.execute(
            """
            SELECT id, name, email, monthly_income::float, savings_goal::float, risk_tolerance,
                   last_login
            FROM users WHERE id = %s;
            """,
            (user_id,),
        )
        ur = cur.fetchone()
        if not ur:
            raise HTTPException(404, "User not found")
        user = UserResponse(
            id=ur[0],
            name=ur[1],
            email=ur[2],
            monthly_income=float(ur[3]),
            savings_goal=float(ur[4]),
            risk_tolerance=ur[5],
        )
        last_login = ur[6]

        # Real "Last synced" — most-recent bank sync across all linked banks.
        # Returns NULL when the user has not linked any bank yet; the frontend
        # then falls back to last_login or hides the timestamp gracefully.
        cur.execute(
            """
            SELECT MAX(last_synced)
            FROM bank_connections
            WHERE user_id = %s AND last_synced IS NOT NULL;
            """,
            (user_id,),
        )
        ls_row = cur.fetchone()
        last_synced = ls_row[0] if ls_row else None

        # Pending fraud signals — drives the greeting status pill
        # ("FraudShield is watching N signals"). PENDING = awaiting user action.
        cur.execute(
            """
            SELECT COUNT(*) FROM fraud_alerts
            WHERE user_id = %s
              AND COALESCE(user_action, 'PENDING') = 'PENDING';
            """,
            (user_id,),
        )
        fraud_pending = int(cur.fetchone()[0] or 0)
        cur.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN type = 'CREDIT' THEN amount ELSE 0 END), 0)::float,
                   COALESCE(SUM(CASE WHEN type = 'DEBIT' THEN amount ELSE 0 END), 0)::float,
                   COUNT(*)
            FROM transactions
            WHERE user_id = %s
              AND EXTRACT(MONTH FROM transaction_date)::int = %s
              AND EXTRACT(YEAR FROM transaction_date)::int = %s;
            """,
            (user_id, m, y),
        )
        inc, exp, cnt = cur.fetchone()
        current_month = {
            "year": y,
            "month": m,
            "total_income": float(inc or 0),
            "total_expense": float(exp or 0),
            "saved": round(float(inc or 0) - float(exp or 0), 2),
            "transaction_count": int(cnt or 0),
        }

        cur.execute(
            """
            SELECT id, merchant, amount, transaction_date, COALESCE(anomaly_reason, ''),
                   risk_score, risk_level
            FROM transactions
            WHERE user_id = %s AND anomaly_flag = TRUE
            ORDER BY transaction_date DESC LIMIT 8;
            """,
            (user_id,),
        )
        anoms = []
        for r in cur.fetchall():
            reason = r[4] or ""
            atype = reason.split(":", 1)[0].strip() if ":" in reason else "ANOMALY"
            anoms.append(
                AnomalyResponse(
                    transaction_id=r[0],
                    merchant=r[1] or "",
                    amount=float(r[2]),
                    transaction_date=r[3],
                    anomaly_type=atype[:80],
                    risk_score=int(r[5] or 0),
                    risk_level=r[6] or "LOW",
                    reason=reason,
                )
            )

        pm, py = (m - 1, y) if m > 1 else (12, y - 1)
        cur.execute(
            """
            WITH cur AS (
                SELECT COALESCE(category, 'Uncategorized') AS category,
                       SUM(amount)::float AS total, COUNT(*)::int AS cnt
                FROM transactions
                WHERE user_id = %s AND type = 'DEBIT'
                  AND EXTRACT(MONTH FROM transaction_date)::int = %s
                  AND EXTRACT(YEAR FROM transaction_date)::int = %s
                GROUP BY 1
            ),
            prev AS (
                SELECT COALESCE(category, 'Uncategorized') AS category, SUM(amount)::float AS total
                FROM transactions
                WHERE user_id = %s AND type = 'DEBIT'
                  AND EXTRACT(MONTH FROM transaction_date)::int = %s
                  AND EXTRACT(YEAR FROM transaction_date)::int = %s
                GROUP BY 1
            )
            SELECT cur.category, cur.total, cur.cnt, COALESCE(prev.total, 0)::float
            FROM cur LEFT JOIN prev ON prev.category = cur.category;
            """,
            (user_id, m, y, user_id, pm, py),
        )
        rows = cur.fetchall()
        grand = sum(r[1] or 0 for r in rows) or 1.0
        spending: list[SpendingAnalysis] = []
        for cat, total, cnt, prev_total in rows:
            total_f = float(total or 0)
            prev_f = float(prev_total or 0)
            if prev_f <= 0 and total_f > 0:
                tr = "UP"
            elif total_f > prev_f * 1.05:
                tr = "UP"
            elif total_f < prev_f * 0.95 and prev_f > 0:
                tr = "DOWN"
            else:
                tr = "STABLE"
            spending.append(
                SpendingAnalysis(
                    category=cat,
                    total_amount=round(total_f, 2),
                    transaction_count=int(cnt or 0),
                    percentage=round(total_f / grand * 100, 2),
                    avg_transaction=round(total_f / max(cnt, 1), 2),
                    trend=tr,
                )
            )
        spending.sort(key=lambda x: x.total_amount, reverse=True)

        cur.execute(
            """
            SELECT year, month, total_income::float, total_expense::float, total_saved::float,
                   COALESCE(health_score, 0), COALESCE(anomaly_count, 0)
            FROM monthly_summary
            WHERE user_id = %s
            ORDER BY year DESC, month DESC
            LIMIT 12;
            """,
            (user_id,),
        )
        trends_raw = cur.fetchall()
        trends: list[MonthlyTrend] = []
        for r in reversed(trends_raw):
            trends.append(
                MonthlyTrend(
                    month=f"{int(r[0])}-{int(r[1]):02d}",
                    income=float(r[2] or 0),
                    expense=float(r[3] or 0),
                    saved=float(r[4] or 0),
                    health_score=int(r[5] or 0),
                    anomaly_count=int(r[6] or 0),
                )
            )

        cur.execute(
            "SELECT COUNT(*) FROM alerts WHERE user_id = %s AND is_read = FALSE;",
            (user_id,),
        )
        unread = int(cur.fetchone()[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()

    hs = calculate_health_score(conn, user_id, m, y)

    return DashboardSummary(
        user=user,
        current_month=current_month,
        health_score=hs,
        recent_anomalies=anoms,
        spending_by_category=spending,
        monthly_trends=trends,
        unread_alerts=unread,
        last_synced=last_synced,
        last_login=last_login,
        fraud_pending_count=fraud_pending,
    )


@app.get("/api/business-impact")
def business_impact(conn=Depends(get_db)) -> dict[str, Any]:
    """Compute real business-impact metrics from live DB data."""
    cur = conn.cursor()
    try:
        # Confirmed frauds that were blocked (action = 'BLOCKED')
        cur.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(amount_at_risk), 0)::float
            FROM fraud_alerts
            WHERE user_action = 'BLOCKED';
            """
        )
        row = cur.fetchone()
        total_fraud_prevented = int(row[0] or 0)
        total_money_saved = float(row[1] or 0)

        # Frauds that slipped through (allowed despite being fraud pattern)
        cur.execute(
            "SELECT COUNT(*) FROM fraud_alerts WHERE user_action = 'ALLOWED' AND risk_score >= 60;"
        )
        false_negatives = int(cur.fetchone()[0] or 0)

        # Avg fraud amount
        avg_fraud_amount = (
            round(total_money_saved / total_fraud_prevented, 2) if total_fraud_prevented > 0 else 0.0
        )

        # Detection rate (fraud prevented / total fraud events)
        total_fraud_events = total_fraud_prevented + false_negatives
        detection_rate = (
            round(total_fraud_prevented / total_fraud_events * 100, 1) if total_fraud_events > 0 else 0.0
        )

        # Average fraud attempts per user (approximation)
        cur.execute("SELECT COUNT(DISTINCT user_id) FROM fraud_alerts;")
        user_count = int(cur.fetchone()[0] or 1)
        avg_attempts_per_user = round(total_fraud_events / max(user_count, 1), 2)

        # Projected savings per 1,000 users/year
        projected_savings_per_1000 = round(
            avg_fraud_amount * (detection_rate / 100) * avg_attempts_per_user * 1000, 0
        )

        # Total unique users in system
        cur.execute("SELECT COUNT(*) FROM users;")
        total_users = int(cur.fetchone()[0] or 0)

        inr = "\u20b9"   # ₹ — Indian Rupee sign
        x   = "\u00d7"   # × — multiplication sign
        projection_sentence = (
            f"At {inr}{int(avg_fraud_amount):,} avg fraud loss {x} {detection_rate}% detection rate, "
            f"Fraud Shield prevents {inr}{int(projected_savings_per_1000):,} per 1,000 users/year"
        )

        return {
            "total_fraud_prevented": total_fraud_prevented,
            "total_money_saved_inr": round(total_money_saved, 2),
            "avg_fraud_amount_inr": avg_fraud_amount,
            "detection_rate_pct": detection_rate,
            "false_negatives": false_negatives,
            "avg_fraud_attempts_per_user": avg_attempts_per_user,
            "projected_savings_per_1000_users_inr": projected_savings_per_1000,
            "total_users": total_users,
            "projection_sentence": projection_sentence,
        }
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()


@app.get("/api/trust-score/{user_id}")
def trust_score(user_id: int, conn=Depends(get_db)) -> dict[str, Any]:
    """Compute a 0-1000 trust score from financial health + fraud safety signals."""
    cur = conn.cursor()
    try:
        today = date.today()
        hs = calculate_health_score(conn, user_id, today.month, today.year)
        health = float(hs.score)

        # Derive safety from fraud alerts
        cur.execute(
            "SELECT COALESCE(MAX(risk_score), 0) FROM fraud_alerts WHERE user_id = %s;",
            (user_id,),
        )
        max_risk = int(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COUNT(*) FROM fraud_alerts WHERE user_id = %s;",
            (user_id,),
        )
        attempts = int(cur.fetchone()[0] or 0)
        safety = max(0.0, min(100.0, float(100 - max_risk // 2 - (5 if attempts > 3 else 0))))

        score = round((health * 0.7 + safety * 0.3) * 10, 1)
        return {
            "score": score,
            "health_score": round(health, 1),
            "safety_score": round(safety, 1),
            "formula": "health \u00d7 0.7 + safety \u00d7 0.3, scaled to 1000",
        }
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()
