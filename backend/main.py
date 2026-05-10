"""SmartSpend Analytics API — Phase 2 FastAPI application."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
    analysis,
    anomaly,
    auth,
    dark_patterns,
    emi_detector,
    festival_important_days,
    festival_predictor,
    fraud_shield,
    health_score,
    insights,
    onboarding,
    otp,
    purchase_planner,
    subscription_graveyard,
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

    asyncio.create_task(_warm_ml_models())
    print("SmartSpend Backend Ready (ML training running in background).")

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

app.include_router(auth.router, prefix="/api")
app.include_router(onboarding.router, prefix="/api")
app.include_router(otp.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(anomaly.router, prefix="/api")
app.include_router(health_score.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(emi_detector.router, prefix="/api")
app.include_router(subscription_graveyard.router, prefix="/api")
app.include_router(dark_patterns.router, prefix="/api")
app.include_router(fraud_shield.router, prefix="/api")
app.include_router(festival_important_days.router, prefix="/api")
app.include_router(festival_predictor.router, prefix="/api")
app.include_router(purchase_planner.router, prefix="/api")

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
def health() -> dict[str, str]:
    ok = test_db_connection()
    return {
        "status": "healthy" if ok else "degraded",
        "db": "connected" if ok else "disconnected",
        "ml": "ready",
    }


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
        cur.execute(
            """
            SELECT id, name, email, monthly_income::float, savings_goal::float, risk_tolerance
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
    )
