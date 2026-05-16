"""AI Insights Engine — Phase 4 (OpenAI GPT-4o-mini + Rule-based Fallback)."""

from __future__ import annotations

import calendar
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import date, datetime
from pathlib import Path
from typing import Any, Generator

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from db import get_connection, get_db
from services.dashboard_scope import fetch_dashboard_mode, transaction_scope_sql
from services.openai_service import (
    explain_anomaly_transaction,
    generate_health_narrative,
    generate_monthly_insights,
    get_personalized_recommendations,
    simulate_financial_scenario,
)
from services.scorer import calculate_health_score

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")

router = APIRouter(prefix="/insights", tags=["AI Insights"])
_log = logging.getLogger(__name__)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + month + delta
    ny = (idx - 1) // 12
    nm = (idx - 1) % 12 + 1
    return ny, nm


def build_user_data(conn, user_id: int, month: int, year: int) -> dict[str, Any]:
    """
    Fetch real PostgreSQL data for GPT prompts: profile, monthly_summary
    (or live aggregates), category breakdown, merchants, last month.
    """
    cur = conn.cursor()
    try:
        mode = fetch_dashboard_mode(cur, user_id)
        scope = transaction_scope_sql("t", mode)

        cur.execute(
            """
            SELECT id, name, email, monthly_income::float, savings_goal::float
            FROM users WHERE id = %s;
            """,
            (user_id,),
        )
        ur = cur.fetchone()
        if not ur:
            raise HTTPException(status_code=404, detail="User not found")

        uid, name, email, monthly_income, savings_goal = ur
        monthly_income = float(monthly_income or 0)
        savings_goal = float(savings_goal or 0)

        cur.execute(
            """
            SELECT COALESCE(total_income, 0)::float, COALESCE(total_expense, 0)::float,
                   COALESCE(total_saved, 0)::float, COALESCE(savings_rate, 0)::float,
                   COALESCE(health_score, 0)::int, COALESCE(anomaly_count, 0)::int
            FROM monthly_summary
            WHERE user_id = %s AND month = %s AND year = %s;
            """,
            (user_id, month, year),
        )
        ms = cur.fetchone()
        if ms:
            total_income, total_expense, total_saved, savings_rate, _ms_health, anomaly_count = ms
            total_income = float(total_income or 0)
            total_expense = float(total_expense or 0)
            total_saved = float(total_saved or 0)
            savings_rate = float(savings_rate or 0)
            anomaly_count = int(anomaly_count or 0)
        else:
            cur.execute(
                f"""
                SELECT COALESCE(SUM(CASE WHEN t.type = 'CREDIT' THEN t.amount ELSE 0 END), 0)::float,
                       COALESCE(SUM(CASE WHEN t.type = 'DEBIT' THEN t.amount ELSE 0 END), 0)::float
                FROM transactions t
                WHERE t.user_id = %s
                  AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
                  AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
                  AND ({scope});
                """,
                (user_id, month, year),
            )
            inc, exp = cur.fetchone()
            total_income = float(inc or 0)
            total_expense = float(exp or 0)
            total_saved = round(total_income - total_expense, 2)
            savings_rate = (
                round(total_saved / total_income * 100, 2) if total_income > 0 else 0.0
            )
            cur.execute(
                f"""
                SELECT COUNT(*)::int FROM transactions t
                WHERE t.user_id = %s AND t.anomaly_flag = TRUE
                  AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
                  AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
                  AND ({scope});
                """,
                (user_id, month, year),
            )
            anomaly_count = int(cur.fetchone()[0] or 0)

        hs_live = calculate_health_score(conn, user_id, month, year)
        health_score = int(hs_live.score)

        cur.execute(
            f"""
            SELECT COALESCE(t.category, 'Uncategorized') AS c, SUM(t.amount)::float AS amt
            FROM transactions t
            WHERE t.user_id = %s AND t.type = 'DEBIT'
              AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
              AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
              AND ({scope})
            GROUP BY 1 ORDER BY amt DESC LIMIT 12;
            """,
            (user_id, month, year),
        )
        cat_rows = cur.fetchall()
        grand_debit = sum(float(r[1] or 0) for r in cat_rows) or 1.0
        category_breakdown: list[dict[str, Any]] = []
        for cname, amt in cat_rows[:6]:
            a = float(amt or 0)
            category_breakdown.append(
                {
                    "category": cname,
                    "amount": round(a, 2),
                    "percentage": round(a / grand_debit * 100, 1),
                }
            )

        cur.execute(
            f"""
            SELECT t.merchant, SUM(t.amount)::float AS s
            FROM transactions t
            WHERE t.user_id = %s AND t.type = 'DEBIT' AND t.merchant IS NOT NULL
              AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
              AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
              AND ({scope})
            GROUP BY t.merchant ORDER BY s DESC LIMIT 5;
            """,
            (user_id, month, year),
        )
        top_merchants = [str(r[0]) for r in cur.fetchall() if r[0]]

        py, pm = _shift_month(year, month, -1)
        cur.execute(
            """
            SELECT COALESCE(total_expense, 0)::float, COALESCE(total_saved, 0)::float
            FROM monthly_summary
            WHERE user_id = %s AND month = %s AND year = %s;
            """,
            (user_id, pm, py),
        )
        lm = cur.fetchone()
        if lm:
            last_month_expense, last_month_saved = float(lm[0] or 0), float(lm[1] or 0)
        else:
            cur.execute(
                f"""
                SELECT COALESCE(SUM(CASE WHEN t.type = 'CREDIT' THEN t.amount ELSE 0 END), 0)::float,
                       COALESCE(SUM(CASE WHEN t.type = 'DEBIT' THEN t.amount ELSE 0 END), 0)::float
                FROM transactions t
                WHERE t.user_id = %s
                  AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
                  AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
                  AND ({scope});
                """,
                (user_id, pm, py),
            )
            li, lx = cur.fetchone()
            li, lx = float(li or 0), float(lx or 0)
            last_month_expense = lx
            last_month_saved = round(li - lx, 2)

        current_month_label = f"{calendar.month_name[month]} {year}"

        return {
            "user_id": int(uid),
            "name": name,
            "email": email,
            "monthly_income": monthly_income,
            "savings_goal": savings_goal,
            "current_month": current_month_label,
            "total_income": total_income,
            "total_expense": total_expense,
            "total_saved": total_saved,
            "savings_rate": savings_rate,
            "health_score": health_score,
            "anomaly_count": anomaly_count,
            "category_breakdown": category_breakdown,
            "top_merchants": top_merchants,
            "last_month_expense": last_month_expense,
            "last_month_saved": last_month_saved,
        }
    finally:
        cur.close()


def _health_details_for_narrative(hs: Any) -> dict[str, Any]:
    comp = hs.components or {}
    mapped = {
        "savings_rate_score": int(comp.get("savings_points", 0)),
        "anomaly_penalty": int(comp.get("anomaly_points", 0)),
        "expense_ratio_score": int(comp.get("expense_points", 0)),
        "consistency_score": int(comp.get("consistency_points", 0)),
        "diversity_score": int(comp.get("diversity_points", 0)),
    }
    weakest_key = min(
        [
            ("savings_rate_score", mapped["savings_rate_score"], 30),
            ("anomaly_penalty", mapped["anomaly_penalty"], 20),
            ("expense_ratio_score", mapped["expense_ratio_score"], 25),
            ("consistency_score", mapped["consistency_score"], 15),
            ("diversity_score", mapped["diversity_score"], 10),
        ],
        key=lambda x: x[1] / max(x[2], 1),
    )[0]
    return {
        "score": int(hs.score),
        "grade": hs.grade,
        "components": mapped,
        "trend": hs.trend,
        "weakest_component": weakest_key,
    }


# --- Static paths must be registered before /{user_id} ---


def _insights_payload(conn, user_id: int, month: int, year: int) -> dict[str, Any]:
    user_data = build_user_data(conn, user_id, month, year)
    with ThreadPoolExecutor(max_workers=2) as pool:
        fi = pool.submit(generate_monthly_insights, user_data)
        fr = pool.submit(get_personalized_recommendations, user_data)
        insights = fi.result(timeout=40)
        recommendations = fr.result(timeout=40)
    return {
        "user": {"name": user_data["name"], "email": user_data["email"]},
        "period": user_data["current_month"],
        "insights": insights,
        "recommendations": recommendations,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def _sse_line(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"


@router.get("/{user_id}/insights-stream")
def insights_stream(
    user_id: int,
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000, le=2100),
):
    """SSE: progress pulses while the insights LLM runs; `done` fires as soon as insights return (no second LLM wait)."""

    today = date.today()
    m = month if month is not None else today.month
    y = year if year is not None else today.year

    def event_gen() -> Generator[str, None, None]:
        # Own DB connection for the whole stream — `Depends(get_db)` is torn down as soon as this
        # route returns StreamingResponse, which closes psycopg2 before the generator runs further.
        conn = get_connection()
        try:
            yield _sse_line({"status": "analyzing"})
            # DB work can take several seconds; keep sending pulses so the client/proxy
            # does not treat the SSE as stalled. Same executor runs tasks sequentially.
            with ThreadPoolExecutor(max_workers=1) as pool:
                f_ud = pool.submit(build_user_data, conn, user_id, m, y)
                deadline_ud = time.time() + 45
                while not f_ud.done():
                    if time.time() > deadline_ud:
                        yield _sse_line(
                            {
                                "error": "insights_unavailable",
                                "message": "Loading your profile is taking too long. Please try again.",
                            }
                        )
                        return
                    yield _sse_line({"pulse": True})
                    time.sleep(0.22)
                try:
                    user_data = f_ud.result(timeout=0)
                except HTTPException as exc:
                    yield _sse_line(
                        {
                            "error": "insights_unavailable",
                            "message": str(exc.detail)
                            if not isinstance(exc.detail, dict)
                            else exc.detail.get("message", "Insights unavailable."),
                        }
                    )
                    return
                except Exception:
                    _log.exception("insights-stream build_user_data failed user_id=%s", user_id)
                    yield _sse_line(
                        {
                            "error": "insights_unavailable",
                            "message": "AI insights are temporarily unavailable. Please try again in a moment.",
                        }
                    )
                    return

                fi = pool.submit(generate_monthly_insights, user_data)
                deadline = time.time() + 40
                while not fi.done():
                    if time.time() > deadline:
                        yield _sse_line(
                            {
                                "error": "insights_unavailable",
                                "message": "AI insights are temporarily unavailable. Please try again in a moment.",
                            }
                        )
                        return
                    yield _sse_line({"pulse": True})
                    time.sleep(0.22)
                try:
                    insights = fi.result(timeout=0)
                except Exception:
                    _log.exception("insights-stream generate_monthly_insights failed user_id=%s", user_id)
                    yield _sse_line(
                        {
                            "error": "insights_unavailable",
                            "message": "AI insights are temporarily unavailable. Please try again in a moment.",
                        }
                    )
                    return

            payload = {
                "user": {"name": user_data["name"], "email": user_data["email"]},
                "period": user_data["current_month"],
                "insights": insights,
                "recommendations": {},
                "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            yield _sse_line({"done": True, "data": payload})
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{user_id}/quick-summary")
def quick_summary(
    user_id: int,
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000, le=2100),
    conn=Depends(get_db),
):
    today = date.today()
    m = month if month is not None else today.month
    y = year if year is not None else today.year
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT name FROM users WHERE id = %s;",
            (user_id,),
        )
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="User not found")
        display_name = r[0]

        _mode = fetch_dashboard_mode(cur, user_id)
        _scope = transaction_scope_sql("t", _mode)

        cur.execute(
            f"""
            SELECT COALESCE(SUM(CASE WHEN t.type = 'CREDIT' THEN t.amount ELSE 0 END), 0)::float,
                   COALESCE(SUM(CASE WHEN t.type = 'DEBIT' THEN t.amount ELSE 0 END), 0)::float
            FROM transactions t
            WHERE t.user_id = %s
              AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
              AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
              AND ({_scope});
            """,
            (user_id, m, y),
        )
        inc, exp = cur.fetchone()
        inc_f, exp_f = float(inc or 0), float(exp or 0)
        this_month_saved = round(inc_f - exp_f, 2)
        savings_rate = round(this_month_saved / inc_f * 100, 2) if inc_f > 0 else 0.0

        hs = calculate_health_score(conn, user_id, m, y)

        cur.execute(
            "SELECT COUNT(*)::int FROM alerts WHERE user_id = %s AND is_read = FALSE;",
            (user_id,),
        )
        alerts_pending = int(cur.fetchone()[0] or 0)

        cur.execute(
            f"""
            SELECT COALESCE(t.category, 'Uncategorized'), SUM(t.amount)::float
            FROM transactions t
            WHERE t.user_id = %s AND t.type = 'DEBIT'
              AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
              AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
              AND ({_scope})
            GROUP BY 1 ORDER BY 2 DESC LIMIT 1;
            """,
            (user_id, m, y),
        )
        tc = cur.fetchone()
        top_spend_category = str(tc[0]) if tc else "N/A"

        dim = calendar.monthrange(y, m)[1]
        if m == today.month and y == today.year:
            days_left_in_month = max(0, dim - today.day)
            day_idx = max(1, today.day)
            projected_month_end_savings = round(this_month_saved * (dim / day_idx), 2)
        else:
            days_left_in_month = 0
            projected_month_end_savings = round(this_month_saved, 2)

        cur.execute(
            """
            SELECT year, month, COALESCE(total_saved, 0)::float
            FROM monthly_summary
            WHERE user_id = %s
            ORDER BY year DESC, month DESC
            LIMIT 24;
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        streak = 0
        for yr, mo, saved in rows:
            if float(saved or 0) > 0:
                streak += 1
            else:
                break
        if streak >= 3:
            streak_message = f"{streak} months in a row with positive savings! 🔥"
        elif streak >= 1:
            streak_message = f"{streak} month(s) with positive savings — keep it up!"
        else:
            streak_message = "Start a savings streak this month — even small amounts count."

        h = datetime.now().hour
        if h < 12:
            greet = "Good morning"
        elif h < 17:
            greet = "Good afternoon"
        else:
            greet = "Good evening"
        greeting = f"{greet}, {display_name}! 👋"

        return {
            "greeting": greeting,
            "this_month_saved": this_month_saved,
            "savings_rate": savings_rate,
            "health_score": hs.score,
            "health_grade": hs.grade,
            "alerts_pending": alerts_pending,
            "top_spend_category": top_spend_category,
            "days_left_in_month": days_left_in_month,
            "projected_month_end_savings": projected_month_end_savings,
            "streak_message": streak_message,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quick summary error: {e}") from e
    finally:
        cur.close()


@router.get("/{user_id}/health-narrative")
def health_narrative(
    user_id: int,
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000, le=2100),
    conn=Depends(get_db),
):
    today = date.today()
    m = month if month is not None else today.month
    y = year if year is not None else today.year
    try:
        user_data = build_user_data(conn, user_id, m, y)
        hs = calculate_health_score(conn, user_id, m, y)
        details = _health_details_for_narrative(hs)
        narrative = generate_health_narrative(user_data, details)
        return {
            "user": {"name": user_data["name"], "email": user_data["email"]},
            "period": user_data["current_month"],
            "health_score": hs.model_dump(),
            "health_details": details,
            "narrative": narrative,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {e}") from e


@router.get("/{user_id}/anomaly/{transaction_id}")
def anomaly_explanation(user_id: int, transaction_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM users WHERE id = %s;", (user_id,))
        ur = cur.fetchone()
        if not ur:
            raise HTTPException(status_code=404, detail="User not found")
        user_name = ur[0]

        cur.execute(
            """
            SELECT id, merchant, amount, transaction_date, transaction_time, category,
                   risk_score, risk_level, COALESCE(anomaly_reason, ''), payment_method
            FROM transactions
            WHERE id = %s AND user_id = %s;
            """,
            (transaction_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Transaction not found")

        tx = {
            "merchant": row[1] or "",
            "amount": float(row[2] or 0),
            "transaction_date": str(row[3]),
            "transaction_time": str(row[4]),
            "category": row[5] or "",
            "risk_score": int(row[6] or 0),
            "risk_level": row[7] or "LOW",
            "anomaly_reason": row[8] or "Flagged by SmartSpend",
            "payment_method": row[9] or "",
            "user_name": user_name,
        }
        explanation = explain_anomaly_transaction(tx)
        return {
            "transaction_id": transaction_id,
            "merchant": tx["merchant"],
            "amount": tx["amount"],
            "risk_level": tx["risk_level"],
            "explanation": explanation,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {e}") from e
    finally:
        cur.close()


def _rule_based_simulate(user_data: dict[str, Any], conn, user_id: int, scenario: str) -> dict[str, Any]:
    """
    Compute exact financial impact from real DB data without any LLM.
    Parses common Indian fintech scenario patterns and returns precise numbers.
    """
    income = float(user_data.get("monthly_income") or 0)
    expense = float(user_data.get("total_expense") or 0)
    saved = float(user_data.get("total_saved") or 0)
    savings_rate = float(user_data.get("savings_rate") or 0)
    health = int(user_data.get("health_score") or 0)
    cats = user_data.get("category_breakdown") or []

    s = scenario.lower().strip()

    income_delta = 0.0
    expense_delta = 0.0
    label = scenario
    advice_lines: list[str] = []
    alternatives: list[str] = []

    # --- Parse: "salary cut X%" / "income drop X%"
    m = re.search(r"salary.{0,12}cut\s+(\d+)\s*%|income.{0,6}drop\s+(\d+)\s*%|salary.{0,6}(\d+)\s*%", s)
    if m:
        pct = float(next(x for x in m.groups() if x))
        income_delta = -income * pct / 100
        label = f"Salary cut {pct:.0f}%"
        advice_lines.append(
            f"A {pct:.0f}% salary cut reduces your income by ₹{abs(income_delta):,.0f}/month, "
            f"dropping monthly savings from ₹{saved:,.0f} to ₹{max(saved + income_delta, 0):,.0f}."
        )
        if saved + income_delta < 0:
            advice_lines.append("This puts you in deficit — consider pausing discretionary spend immediately.")
        alternatives = [
            f"Negotiate a {pct/2:.0f}% temporary cut instead of {pct:.0f}%",
            "Cut ₹" + f"{abs(income_delta * 0.5):,.0f} from non-essential categories to partially absorb the impact",
        ]

    # --- Parse: "food/shopping/category +X%" / "spend X% more on Y"
    m2 = re.search(r"(food|shopping|dining|travel|entertainment|grocery|groceries|rent|emi)\s*(spending)?\s*[+](\d+)\s*%", s)
    if not income_delta and not expense_delta and m2:
        cat_name = m2.group(1).title()
        pct = float(m2.group(3))
        cat_amt = next((float(c["amount"]) for c in cats if cat_name.lower() in c.get("category", "").lower()), expense * 0.15)
        expense_delta = cat_amt * pct / 100
        label = f"{cat_name} spending +{pct:.0f}%"
        advice_lines.append(
            f"Increasing {cat_name} spend by {pct:.0f}% adds ₹{expense_delta:,.0f}/month "
            f"(based on your actual ₹{cat_amt:,.0f} {cat_name} spend)."
        )
        advice_lines.append(f"This cuts your savings by ₹{expense_delta:,.0f} to ₹{max(saved - expense_delta, 0):,.0f}.")
        alternatives = [
            f"Cap {cat_name} increase at +{pct/2:.0f}% (saves ₹{expense_delta/2:,.0f}/month)",
            f"Offset with ₹{expense_delta:,.0f} cut from your next-highest spending category",
        ]

    # --- Parse: "start SIP X" / "invest X"
    m3 = re.search(r"(?:start|begin|add)\s+(?:rs\.?\s*)?(\d[\d,]*)\s*(?:sip|investment|invest|mutual fund)", s)
    if not income_delta and not expense_delta and m3:
        sip_amt = float(m3.group(1).replace(",", ""))
        expense_delta = sip_amt
        label = f"Start ₹{sip_amt:,.0f} SIP"
        advice_lines.append(
            f"A ₹{sip_amt:,.0f}/month SIP reduces liquid savings by ₹{sip_amt:,.0f} but builds long-term wealth."
        )
        annual = sip_amt * 12 * 1.12
        advice_lines.append(f"At 12% annual return, ₹{sip_amt:,.0f}/month SIP grows to ~₹{annual:,.0f} in 1 year.")
        if saved - sip_amt < 2000:
            advice_lines.append(
                f"Warning: This leaves only ₹{max(saved - sip_amt, 0):,.0f} liquid. "
                "Keep at least 2 months expenses as emergency buffer."
            )
        alternatives = [
            f"Start with ₹{sip_amt/2:,.0f} SIP first, scale after building ₹{expense * 3:,.0f} emergency fund",
            "Consider ELSS funds — same SIP but with 80C tax deduction benefit",
        ]

    # --- Parse: "add rent X" / "new rent X"
    m4 = re.search(r"(?:add|new|pay|paying)\s+(?:rs\.?\s*)?(\d[\d,]*)\s*(?:rent|house\s*rent)", s)
    if not income_delta and not expense_delta and m4:
        rent = float(m4.group(1).replace(",", ""))
        expense_delta = rent
        label = f"Add ₹{rent:,.0f} rent"
        advice_lines.append(
            f"Adding ₹{rent:,.0f} rent reduces monthly savings to ₹{max(saved - rent, 0):,.0f}."
        )
        rent_to_income = rent / income * 100 if income > 0 else 0
        if rent_to_income > 30:
            advice_lines.append(f"This rent is {rent_to_income:.0f}% of income — above the recommended 30% threshold. Consider co-living.")
        else:
            advice_lines.append(f"This rent is {rent_to_income:.0f}% of income — within safe limits.")
        alternatives = [
            f"Look for accommodation at ₹{rent * 0.75:,.0f} (25% cheaper) to save ₹{rent * 0.25:,.0f}/month",
            "Negotiate rent-free first month to reduce immediate impact",
        ]

    # --- Fetch EMI and goal commitments from DB for richer output
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COALESCE(SUM(emi_amount),0)::float FROM emi_records WHERE user_id=%s AND is_active=TRUE",
            (user_id,)
        )
        total_emi = float(cur.fetchone()[0] or 0)

        cur.execute(
            "SELECT COUNT(*) FROM purchase_goals WHERE user_id=%s AND status='active'",
            (user_id,)
        )
        active_goals = int(cur.fetchone()[0] or 0)

        cur.execute(
            "SELECT COUNT(*) FROM festival_budgets WHERE user_id=%s AND festival_date > CURRENT_DATE",
            (user_id,)
        )
        upcoming_festivals = int(cur.fetchone()[0] or 0)
    except Exception:
        total_emi = 0
        active_goals = 0
        upcoming_festivals = 0
    finally:
        cur.close()

    # --- Compute projected state
    proj_income = income + income_delta
    proj_expense = expense + expense_delta
    proj_saved = proj_income - proj_expense
    proj_savings_rate = round(proj_saved / proj_income * 100, 1) if proj_income > 0 else 0.0

    savings_change = proj_saved - saved
    savings_change_pct = round(savings_change / saved * 100, 1) if saved != 0 else 0.0
    annual_impact = round(savings_change * 12, 0)

    health_delta = 0
    if proj_savings_rate >= 20:
        health_delta = 5
    elif proj_savings_rate <= 0:
        health_delta = -25
    elif proj_savings_rate < 5:
        health_delta = -15
    elif proj_savings_rate < 10:
        health_delta = -8
    else:
        health_delta = -3
    proj_health = max(0, min(100, health + health_delta))

    if proj_saved < 0:
        verdict = "CRITICAL"
    elif proj_savings_rate < 5 or abs(savings_change) > income * 0.2:
        verdict = "RISKY"
    else:
        verdict = "MANAGEABLE"

    if not advice_lines:
        advice_lines.append(
            f"This scenario changes your monthly savings from ₹{saved:,.0f} to ₹{proj_saved:,.0f}."
        )

    # Context: existing EMI and goal burden
    if total_emi > 0:
        advice_lines.append(
            f"Note: You already carry ₹{total_emi:,.0f}/month in active EMIs"
            + (f" and have {active_goals} active purchase goal(s)" if active_goals else "")
            + " — factor these into any new commitment."
        )
    if upcoming_festivals > 0:
        advice_lines.append(f"You have {upcoming_festivals} upcoming festival(s) to budget for as well.")

    return {
        "scenario_title": label,
        "current_state": {
            "monthly_savings": round(saved, 0),
            "health_score": health,
            "savings_rate": round(savings_rate, 1),
        },
        "projected_state": {
            "monthly_savings": round(proj_saved, 0),
            "health_score": proj_health,
            "savings_rate": proj_savings_rate,
        },
        "impact": {
            "savings_change": round(savings_change, 0),
            "savings_change_pct": savings_change_pct,
            "health_score_change": health_delta,
            "annual_impact": annual_impact,
            "emi_burden": round(total_emi, 0),
            "active_goals": active_goals,
            "upcoming_festivals": upcoming_festivals,
        },
        "verdict": verdict,
        "advice": " ".join(advice_lines),
        "alternatives": alternatives,
        "computed_from": "real_transactions",
    }


class SimulationRequest(BaseModel):
    scenario: str = Field(..., min_length=3, max_length=800)
    month: int = Field(default_factory=lambda: date.today().month, ge=1, le=12)
    year: int = Field(default_factory=lambda: date.today().year, ge=2000, le=2100)


@router.post("/{user_id}/simulate")
def simulate(user_id: int, body: SimulationRequest, conn=Depends(get_db)):
    try:
        user_data = build_user_data(conn, user_id, body.month, body.year)

        # Try LLM first; fall back to deterministic rule-based engine
        ai_result = simulate_financial_scenario(user_data, body.scenario)
        if ai_result.get("verdict") not in (None, "", "UNKNOWN"):
            ai_result["computed_from"] = "ai"
            return ai_result

        return _rule_based_simulate(user_data, conn, user_id, body.scenario)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation error: {e}") from e


@router.get("/{user_id}")
def get_insights(
    user_id: int,
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000, le=2100),
    conn=Depends(get_db),
):
    today = date.today()
    m = month if month is not None else today.month
    y = year if year is not None else today.year
    try:
        return _insights_payload(conn, user_id, m, y)
    except HTTPException:
        raise
    except FuturesTimeout:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "insights_unavailable",
                "message": "AI insights are temporarily unavailable. Please try again in a moment.",
            },
        ) from None
    except Exception:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "insights_unavailable",
                "message": "AI insights are temporarily unavailable. Please try again in a moment.",
            },
        ) from None
