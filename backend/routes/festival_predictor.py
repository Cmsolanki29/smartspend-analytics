"""Festival overspend predictor — calendar, budgets, Groq-backed English advice."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_db
from services.ai_service import call_groq
from services.dashboard_scope import fetch_dashboard_mode, transaction_scope_sql

router = APIRouter(prefix="/festivals", tags=["Festival Predictor"])

INDIAN_FESTIVALS_2026: list[dict[str, Any]] = [
    {"name": "Holi", "date": "2026-03-29", "typical_categories": ["Clothes", "Food", "Colors"]},
    {"name": "Eid al-Fitr", "date": "2026-03-31", "typical_categories": ["Clothes", "Food", "Gifts"]},
    {"name": "Navratri", "date": "2026-10-02", "typical_categories": ["Clothes", "Jewelry", "Events"]},
    {"name": "Dussehra", "date": "2026-10-11", "typical_categories": ["Shopping", "Food", "Travel"]},
    {"name": "Diwali", "date": "2026-10-20", "typical_categories": ["Gifts", "Shopping", "Food", "Crackers", "Travel"]},
    {"name": "Christmas", "date": "2026-12-25", "typical_categories": ["Gifts", "Food", "Travel"]},
    {"name": "New Year", "date": "2026-12-31", "typical_categories": ["Party", "Travel", "Shopping"]},
]


def _norm_name(s: str) -> str:
    x = (s or "").strip().lower()
    x = x.replace(" al-fitr", "").replace(" al fitr", "")
    return x


def _match_db_name(cal_name: str, db_name: str) -> bool:
    a, b = _norm_name(cal_name), _norm_name(db_name)
    if a == b:
        return True
    if "eid" in a and "eid" in b:
        return True
    pa, pb = a.split(), b.split()
    if pa and pb and pa[0] == pb[0]:
        return True
    return False


def _urgency(days: int) -> str:
    if days < 7:
        return "CRITICAL"
    if days < 30:
        return "URGENT"
    if days <= 90:
        return "START_SAVING"
    return "PLAN_NOW"


def _user_income(conn, user_id: int) -> float:
    cur = conn.cursor()
    cur.execute("SELECT monthly_income::float FROM users WHERE id = %s;", (user_id,))
    row = cur.fetchone()
    cur.close()
    return float(row[0] or 0) if row else 0.0


def _avg_monthly_saved(conn, user_id: int, months: int = 6) -> float:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(AVG(total_saved), 0)::float
        FROM (
          SELECT total_saved FROM monthly_summary
          WHERE user_id = %s
          ORDER BY year DESC, month DESC
          LIMIT %s
        ) t;
        """,
        (user_id, months),
    )
    v = float(cur.fetchone()[0] or 0)
    cur.close()
    return v


def _subscription_monthly_total(conn, user_id: int) -> float:
    """Approximate dead subscription spend from recurring-style merchants (last 90d / 3)."""
    cur = conn.cursor()
    mode = fetch_dashboard_mode(cur, user_id)
    scope = transaction_scope_sql("t", mode)
    cur.execute(
        f"""
        SELECT COALESCE(SUM(t.amount), 0)::float / 3.0
        FROM transactions t
        WHERE t.user_id = %s AND t.type = 'DEBIT'
          AND t.transaction_date >= CURRENT_DATE - INTERVAL '90 days'
          AND ({scope})
          AND (
            LOWER(COALESCE(t.merchant,'')) LIKE '%%netflix%%'
            OR LOWER(COALESCE(t.merchant,'')) LIKE '%%spotify%%'
            OR LOWER(COALESCE(t.merchant,'')) LIKE '%%prime%%'
            OR LOWER(COALESCE(t.merchant,'')) LIKE '%%hotstar%%'
            OR LOWER(COALESCE(t.merchant,'')) LIKE '%%youtube%%'
          );
        """,
        (user_id,),
    )
    v = float(cur.fetchone()[0] or 0)
    cur.close()
    return v


def _food_delivery_monthly(conn, user_id: int) -> float:
    cur = conn.cursor()
    mode = fetch_dashboard_mode(cur, user_id)
    scope = transaction_scope_sql("t", mode)
    cur.execute(
        f"""
        SELECT COALESCE(SUM(t.amount), 0)::float / 3.0
        FROM transactions t
        WHERE t.user_id = %s AND t.type = 'DEBIT'
          AND t.transaction_date >= CURRENT_DATE - INTERVAL '90 days'
          AND ({scope})
          AND (
            LOWER(COALESCE(t.merchant,'')) LIKE '%%swiggy%%'
            OR LOWER(COALESCE(t.merchant,'')) LIKE '%%zomato%%'
            OR LOWER(COALESCE(t.merchant,'')) LIKE '%%uber eats%%'
            OR LOWER(COALESCE(t.category,'')) LIKE '%%food%%'
          );
        """,
        (user_id,),
    )
    v = float(cur.fetchone()[0] or 0)
    cur.close()
    return v


def _fetch_budget_row(conn, user_id: int, fest_name: str, fest_date: date) -> Optional[tuple[Any, ...]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, last_year_spent, planned_budget, saved_so_far, monthly_target,
               days_remaining, status, category_breakdown, festival_name
        FROM festival_budgets
        WHERE user_id = %s AND EXTRACT(YEAR FROM festival_date) = %s;
        """,
        (user_id, fest_date.year),
    )
    rows = cur.fetchall()
    cur.close()
    for r in rows:
        if _match_db_name(fest_name, r[8]):
            return r
    return None


def _parse_groq_triple(text: str) -> tuple[str, str, str]:
    if not text:
        return "", "", ""
    advice = re.search(r"<<<ADVICE>>>\s*(.*?)(?=<<<TIP>>>|$)", text, re.S | re.I)
    tip = re.search(r"<<<TIP>>>\s*(.*?)(?=<<<WARNING>>>|$)", text, re.S | re.I)
    warn = re.search(r"<<<WARNING>>>\s*(.*)$", text, re.S | re.I)
    return (
        (advice.group(1).strip() if advice else "").strip(),
        (tip.group(1).strip() if tip else "").strip(),
        (warn.group(1).strip() if warn else "").strip(),
    )


def generate_festival_ai_blocks(
    user_name: str,
    festival: str,
    user_income: float,
    days_remaining: int,
    last_year_spent: float,
    monthly_saving_needed: float,
    recommended_budget: float,
    saved_so_far: float,
    food_delivery_monthly: float,
    sub_monthly: float,
) -> tuple[str, str, str]:
    system = (
        "You are SmartSpend festival budget advisor. Output plain text ONLY using exactly these "
        "line markers (including angle brackets): <<<ADVICE>>> then paragraph, <<<TIP>>> then one sentence, "
        "<<<WARNING>>> then one short sentence. Write in clear, professional yet friendly English. "
        "Be specific with rupee amounts. Use Indian financial context (UPI, festivals). No Hindi. No JSON."
    )
    facts = (
        f"User name: {user_name}\nFestival: {festival}\nDays left: {days_remaining}\n"
        f"Last year spent: ₹{last_year_spent:.0f}\nRecommended budget: ₹{recommended_budget:.0f}\n"
        f"Saved so far for this festival: ₹{saved_so_far:.0f}\n"
        f"Monthly saving needed: ₹{monthly_saving_needed:.0f}\nMonthly income: ₹{user_income:.0f}\n"
        f"Approx food delivery spend (90d avg monthly): ₹{food_delivery_monthly:.0f}\n"
        f"Approx subscription-like spend (90d avg monthly): ₹{sub_monthly:.0f}\n"
        f"ADVICE: 3-4 sentences — plan, emotional but practical.\n"
        f"TIP: one sentence suggesting concrete cuts using ONLY the numbers above.\n"
        f"WARNING: one sentence — what happens if they do not start saving now (credit stress), use festival name."
    )
    raw = call_groq(system, facts, max_tokens=420, temperature=0.55)
    raw_s = raw if isinstance(raw, str) else ""
    a, t, w = _parse_groq_triple(raw_s)
    if not a and raw_s:
        parts = [p.strip() for p in raw_s.split("\n\n") if p.strip()]
        if len(parts) >= 3:
            return parts[0], parts[1], parts[2]
        if len(parts) == 1:
            return parts[0], "", ""
    if not a:
        a = (
            f"{user_name}, plan early for {festival}: about ₹{recommended_budget:,.0f} is a practical envelope "
            f"based on last year's ₹{last_year_spent:,.0f}. You have {days_remaining} days left to spread the cost evenly."
        )
    if not t:
        t = (
            f"Aim to set aside roughly ₹{monthly_saving_needed:,.0f} per month until then. "
            f"Optional trims: food delivery (~₹{food_delivery_monthly:,.0f}/mo) and subscription-style spend "
            f"(~₹{sub_monthly:,.0f}/mo) if those lines are high in your statement."
        )
    if not w:
        w = (
            f"If you do not start saving for {festival} now, you may lean on cards or EMI later and pay extra interest."
        )
    return a, t, w


@router.get("/{user_id}/history")
def festival_history(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")
    cur.execute(
        """
        SELECT festival_name, festival_date, last_year_spent, planned_budget,
               saved_so_far, category_breakdown, status
        FROM festival_budgets
        WHERE user_id = %s
        ORDER BY festival_date DESC;
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    out = []
    for r in rows:
        cb = r[5]
        if isinstance(cb, str):
            try:
                cb = json.loads(cb)
            except json.JSONDecodeError:
                cb = {}
        out.append(
            {
                "festival_name": r[0],
                "festival_date": r[1].isoformat() if r[1] else None,
                "last_year_spent": float(r[2] or 0),
                "planned_budget": float(r[3] or 0),
                "saved_so_far": float(r[4] or 0),
                "category_breakdown": cb or {},
                "status": r[6],
            }
        )
    return {"history": out}


class SetBudgetBody(BaseModel):
    festival_name: str = Field(..., min_length=1)
    planned_budget: float = Field(..., ge=0)
    category_budgets: dict[str, float] = {}


@router.post("/{user_id}/set-budget")
def set_festival_budget(user_id: int, body: SetBudgetBody, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")

    today = date.today()
    fest_date: Optional[date] = None
    for f in INDIAN_FESTIVALS_2026:
        if _norm_name(f["name"]) == _norm_name(body.festival_name) or _match_db_name(
            body.festival_name, f["name"]
        ):
            fest_date = datetime.strptime(f["date"], "%Y-%m-%d").date()
            break
    if fest_date is None:
        for f in INDIAN_FESTIVALS_2026:
            if body.festival_name.lower() in f["name"].lower():
                fest_date = datetime.strptime(f["date"], "%Y-%m-%d").date()
                break
    if fest_date is None:
        cur.close()
        raise HTTPException(400, "Unknown festival name for 2026 calendar")

    days_rem = (fest_date - today).days
    months_rem = max(days_rem / 30.0, 0.25)
    remaining = max(0.0, float(body.planned_budget) - 0.0)
    monthly_needed = remaining / months_rem if months_rem else 0.0

    cb_json = json.dumps(body.category_budgets or {})

    cur.execute(
        """
        SELECT id, festival_name FROM festival_budgets
        WHERE user_id = %s AND EXTRACT(YEAR FROM festival_date)::int = %s;
        """,
        (user_id, fest_date.year),
    )
    row_id = None
    for rid, fnm in cur.fetchall():
        if _match_db_name(body.festival_name, fnm):
            row_id = rid
            break
    if row_id:
        cur.execute(
            """
            UPDATE festival_budgets
            SET planned_budget = %s, category_breakdown = %s::jsonb,
                days_remaining = %s, monthly_target = %s
            WHERE id = %s;
            """,
            (body.planned_budget, cb_json, days_rem, monthly_needed, row_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO festival_budgets (
              user_id, festival_name, festival_date, last_year_spent, planned_budget,
              saved_so_far, monthly_target, days_remaining, status, category_breakdown
            ) VALUES (%s, %s, %s, 0, %s, 0, %s, %s, 'UPCOMING', %s::jsonb);
            """,
            (
                user_id,
                body.festival_name.strip(),
                fest_date,
                body.planned_budget,
                monthly_needed,
                days_rem,
                cb_json,
            ),
        )
    cur.close()

    return {
        "success": True,
        "festival_name": body.festival_name,
        "planned_budget": body.planned_budget,
        "days_remaining": days_rem,
        "monthly_saving_needed": round(monthly_needed, 2),
        "weekly_saving_needed": round(monthly_needed / 4.33, 2),
        "daily_saving_needed": round(monthly_needed / 30.0, 2),
    }


@router.get("/{user_id}")
def upcoming_festivals(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT name FROM users WHERE id = %s;", (user_id,))
    urow = cur.fetchone()
    if not urow:
        cur.close()
        raise HTTPException(404, "User not found")
    user_name = (urow[0] or "User").strip()
    cur.close()

    today = date.today()
    horizon = date.fromordinal(today.toordinal() + 183)
    income = _user_income(conn, user_id)
    avg_saved = _avg_monthly_saved(conn, user_id)
    food_m = _food_delivery_monthly(conn, user_id)
    sub_m = _subscription_monthly_total(conn, user_id)

    upcoming: list[dict[str, Any]] = []
    total_budget = 0.0
    monthly_sum = 0.0

    for fest in INDIAN_FESTIVALS_2026:
        d = datetime.strptime(fest["date"], "%Y-%m-%d").date()
        if d <= today or d > horizon:
            continue

        days_rem = (d - today).days
        months_rem = max(days_rem / 30.0, 0.25)

        row = _fetch_budget_row(conn, user_id, fest["name"], d)
        last_year = float(row[1] or 0) if row else 0.0
        planned = float(row[2] or 0) if row and row[2] else 0.0
        saved = float(row[3] or 0) if row else 0.0
        cat = row[7] if row else None
        if isinstance(cat, str):
            try:
                cat = json.loads(cat)
            except json.JSONDecodeError:
                cat = {}
        if not isinstance(cat, dict):
            cat = {}

        recommended = planned if planned > 0 else round(last_year * 1.0526) if last_year > 0 else round(income * 0.08)
        gap = max(0.0, recommended - saved)
        monthly_need = gap / months_rem
        weekly_need = monthly_need / 4.33
        daily_need = monthly_need / 30.0

        ai_advice, saving_tip, if_no = generate_festival_ai_blocks(
            user_name,
            fest["name"],
            income,
            days_rem,
            last_year,
            monthly_need,
            recommended,
            saved,
            food_m,
            sub_m,
        )

        urgency = _urgency(days_rem)
        upcoming.append(
            {
                "festival_name": fest["name"],
                "festival_date": fest["date"],
                "days_remaining": days_rem,
                "months_remaining": round(months_rem, 2),
                "last_year_spent": round(last_year, 2),
                "recommended_budget": round(recommended, 2),
                "saved_so_far": round(saved, 2),
                "monthly_saving_needed": round(monthly_need, 2),
                "weekly_saving_needed": round(weekly_need, 2),
                "daily_saving_needed": round(daily_need, 2),
                "urgency": urgency,
                "category_breakdown": cat,
                "ai_advice": ai_advice,
                "saving_tip": saving_tip,
                "if_no_saving_warning": if_no,
            }
        )
        total_budget += recommended
        monthly_sum += monthly_need

    upcoming.sort(key=lambda x: x["days_remaining"])

    next_f = None
    if upcoming:
        nf = upcoming[0]
        next_f = {"name": nf["festival_name"], "days_remaining": nf["days_remaining"], "urgency": nf["urgency"]}

    biggest = ""
    if upcoming:
        biggest = max(upcoming, key=lambda x: x["recommended_budget"])["festival_name"]

    gap_month = max(0.0, monthly_sum - avg_saved)
    gap_items: list[str] = []
    if sub_m > 0:
        gap_items.append(f"Review subscription-style spend (~{round(sub_m):,} ₹/mo) — cancel unused apps.")
    if food_m > 0:
        gap_items.append(f"Trim food delivery (~{round(min(food_m * 0.35, gap_month * 0.5)):,} ₹/mo suggested cut).")

    return {
        "upcoming_festivals": upcoming,
        "total_festival_budget_needed": round(total_budget, 2),
        "months_to_save": round(max([x["months_remaining"] for x in upcoming] or [0]), 2),
        "monthly_total_target": round(monthly_sum, 2),
        "current_savings_rate_monthly": round(avg_saved, 2),
        "gap_vs_current_savings_monthly": round(gap_month, 2),
        "gap_close_suggestions": gap_items,
        "biggest_festival": biggest,
        "next_festival": next_f,
    }
