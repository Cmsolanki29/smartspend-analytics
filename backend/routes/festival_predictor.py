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
from services.financial_constraints import monthly_surplus_snapshot

router = APIRouter(prefix="/festivals", tags=["Festival Predictor"])

HORIZON_DAYS = 183  # preset Indian calendar slots shown in planner
CUSTOM_EVENT_MAX_DAYS = 1825  # user-created plans (weddings, school fees) up to ~5 years

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


def _calendar_lookup(festival_name: str) -> Optional[dict[str, Any]]:
    for fest in INDIAN_FESTIVALS_2026:
        if _match_db_name(festival_name, fest["name"]):
            return fest
    return None


def _calendar_date_for_name(festival_name: str) -> Optional[date]:
    cal = _calendar_lookup(festival_name)
    if not cal:
        return None
    return datetime.strptime(cal["date"], "%Y-%m-%d").date()


def _typical_categories(festival_name: str) -> list[str]:
    cal = _calendar_lookup(festival_name)
    if cal and cal.get("typical_categories"):
        return list(cal["typical_categories"])
    return ["Gifts", "Food", "Travel"]


def _horizon_end(today: date, days: int = HORIZON_DAYS) -> date:
    return date.fromordinal(today.toordinal() + days)


def _resolve_festival_date(
    conn,
    user_id: int,
    festival_name: str,
    explicit: Optional[date] = None,
) -> date:
    if explicit is not None:
        return explicit
    cal_d = _calendar_date_for_name(festival_name)
    if cal_d is not None:
        return cal_d
    cur = conn.cursor()
    cur.execute(
        """
        SELECT festival_date, festival_name
        FROM festival_budgets
        WHERE user_id = %s AND festival_date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY festival_date ASC;
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    for fd, fnm in rows:
        if _match_db_name(festival_name, str(fnm)):
            if isinstance(fd, date):
                return fd
            return datetime.strptime(str(fd)[:10], "%Y-%m-%d").date()
    raise HTTPException(
        400,
        "Unknown event. Add it with “Add event plan” and a future date, or pick a name from the calendar.",
    )


def _fetch_budget_row(conn, user_id: int, fest_name: str, fest_date: date) -> Optional[tuple[Any, ...]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, last_year_spent, planned_budget, saved_so_far, monthly_target,
               days_remaining, status, category_breakdown, festival_name
        FROM festival_budgets
        WHERE user_id = %s AND festival_date = %s;
        """,
        (user_id, fest_date),
    )
    rows = cur.fetchall()
    if not rows:
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


def upsert_festival_budget_row(
    conn,
    user_id: int,
    fest_name: str,
    fest_date: date,
    *,
    planned_budget: float = 0,
    saved_so_far: float = 0,
    category_breakdown: Optional[dict[str, float]] = None,
) -> None:
    """Ensure a user event appears in the festival planner list (any user_id)."""
    today = date.today()
    days_rem = max((fest_date - today).days, 0)
    months_rem = max(days_rem / 30.0, 0.25)
    planned = float(planned_budget or 0)
    saved = float(saved_so_far or 0)
    remaining = max(0.0, planned - saved)
    monthly_needed = remaining / months_rem if months_rem else 0.0
    cb_json = json.dumps(category_breakdown or {})
    row = _fetch_budget_row(conn, user_id, fest_name, fest_date)
    cur = conn.cursor()
    if row:
        cur.execute(
            """
            UPDATE festival_budgets
            SET planned_budget = CASE WHEN %s > 0 THEN %s ELSE planned_budget END,
                saved_so_far = GREATEST(saved_so_far, %s),
                category_breakdown = CASE WHEN %s::jsonb <> '{}'::jsonb THEN %s::jsonb ELSE category_breakdown END,
                days_remaining = %s, monthly_target = %s, festival_date = %s, status = 'UPCOMING'
            WHERE id = %s;
            """,
            (planned, planned, saved, cb_json, cb_json, days_rem, monthly_needed, fest_date, row[0]),
        )
    else:
        cur.execute(
            """
            INSERT INTO festival_budgets (
              user_id, festival_name, festival_date, last_year_spent, planned_budget,
              saved_so_far, monthly_target, days_remaining, status, category_breakdown
            ) VALUES (%s, %s, %s, 0, %s, %s, %s, %s, 'UPCOMING', %s::jsonb);
            """,
            (user_id, fest_name.strip(), fest_date, planned, saved, monthly_needed, days_rem, cb_json),
        )
    cur.close()


def _iter_upcoming_festival_slots(
    conn,
    user_id: int,
    today: date,
    horizon: date,
) -> list[tuple[str, date, bool]]:
    """Return (name, date, is_custom) sorted by date — DB rows plus calendar defaults."""
    custom_horizon = _horizon_end(today, CUSTOM_EVENT_MAX_DAYS)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT festival_name, festival_date
        FROM festival_budgets
        WHERE user_id = %s AND festival_date > %s AND festival_date <= %s
        ORDER BY festival_date ASC, festival_name ASC;
        """,
        (user_id, today, custom_horizon),
    )
    db_rows = cur.fetchall()
    cur.close()

    out: list[tuple[str, date, bool]] = []
    covered: set[tuple[str, str]] = set()
    names_from_db: set[str] = set()

    for fnm, fd in db_rows:
        d = fd if isinstance(fd, date) else datetime.strptime(str(fd)[:10], "%Y-%m-%d").date()
        name = str(fnm)
        key = (_norm_name(name), d.isoformat())
        covered.add(key)
        names_from_db.add(_norm_name(name))
        cal_d = _calendar_date_for_name(name)
        is_custom = cal_d is None or cal_d != d
        out.append((name, d, is_custom))

    for fest in INDIAN_FESTIVALS_2026:
        d = datetime.strptime(fest["date"], "%Y-%m-%d").date()
        if d <= today or d > horizon:
            continue
        if _norm_name(fest["name"]) in names_from_db:
            continue
        key = (_norm_name(fest["name"]), d.isoformat())
        if key in covered:
            continue
        out.append((fest["name"], d, False))

    out.sort(key=lambda x: (x[1], x[0]))
    return out


def _build_festival_payload(
    conn,
    user_id: int,
    user_name: str,
    fest_name: str,
    fest_date: date,
    today: date,
    income: float,
    food_m: float,
    sub_m: float,
    *,
    is_custom: bool = False,
    refresh_ai: bool = True,
) -> dict[str, Any]:
    days_rem = (fest_date - today).days
    months_rem = max(days_rem / 30.0, 0.25)

    row = _fetch_budget_row(conn, user_id, fest_name, fest_date)
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

    ai_advice, saving_tip, if_no = ("", "", "")
    if refresh_ai:
        ai_advice, saving_tip, if_no = generate_festival_ai_blocks(
            user_name,
            fest_name,
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
    progress_pct = round(100.0 * saved / recommended, 1) if recommended > 0 else 0.0
    linked_goals = _linked_purchase_goals(conn, user_id, fest_name, fest_date)
    return {
        "festival_name": fest_name,
        "festival_date": fest_date.isoformat(),
        "days_remaining": days_rem,
        "months_remaining": round(months_rem, 2),
        "last_year_spent": round(last_year, 2),
        "recommended_budget": round(recommended, 2),
        "saved_so_far": round(saved, 2),
        "progress_pct": progress_pct,
        "monthly_saving_needed": round(monthly_need, 2),
        "weekly_saving_needed": round(weekly_need, 2),
        "daily_saving_needed": round(daily_need, 2),
        "urgency": urgency,
        "category_breakdown": cat,
        "linked_goals": linked_goals,
        "ai_advice": ai_advice,
        "saving_tip": saving_tip,
        "if_no_saving_warning": if_no,
        "is_custom": is_custom,
        "suggested_categories": _typical_categories(fest_name),
    }


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
        "line markers (including angle brackets): <<<ADVICE>>> then 1-2 SHORT sentences (max 35 words), "
        "<<<TIP>>> then one short sentence (max 20 words), "
        "<<<WARNING>>> then one short sentence (max 20 words). "
        "Be specific with rupee amounts. No Hindi. No JSON. No generic platitudes."
    )
    facts = (
        f"User name: {user_name}\nFestival: {festival}\nDays left: {days_remaining}\n"
        f"Last year spent: ₹{last_year_spent:.0f}\nRecommended budget: ₹{recommended_budget:.0f}\n"
        f"Saved so far for this festival: ₹{saved_so_far:.0f}\n"
        f"Monthly saving needed: ₹{monthly_saving_needed:.0f}\nMonthly income: ₹{user_income:.0f}\n"
        f"Approx food delivery spend (90d avg monthly): ₹{food_delivery_monthly:.0f}\n"
        f"Approx subscription-like spend (90d avg monthly): ₹{sub_monthly:.0f}\n"
    )
    raw = call_groq(system, facts, max_tokens=220, temperature=0.5)
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
    festival_date: Optional[date] = None


class CreateEventBody(BaseModel):
    festival_name: str = Field(..., min_length=1, max_length=120)
    festival_date: date
    planned_budget: float = Field(default=0, ge=0)
    category_budgets: dict[str, float] = Field(default_factory=dict)


@router.post("/{user_id}/set-budget")
def set_festival_budget(user_id: int, body: SetBudgetBody, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")

    today = date.today()
    fest_date = _resolve_festival_date(conn, user_id, body.festival_name, body.festival_date)

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

    try:
        from services.financial_engine import recalculate_financial_state as _rfs

        _rfs(conn, user_id, "festival_budget_set", None, f"Festival budget set for {body.festival_name}.")
    except Exception:
        pass

    cash = monthly_surplus_snapshot(conn, user_id)
    avail = float(cash["available_monthly_surplus"])
    planned = float(body.planned_budget)
    monthly_festival_burden = monthly_needed
    feasible = monthly_festival_burden <= avail + 1.0
    warning = None
    if not feasible:
        warning = (
            f"Festival saving pace (₹{monthly_festival_burden:,.0f}/mo) exceeds available surplus "
            f"(₹{avail:,.0f}/mo after EMIs and purchase goals). Reduce budget or defer purchases."
        )
    elif planned > avail * max(months_rem, 1) * 1.15 and months_rem < 3:
        warning = (
            f"Lump-sum budget ₹{planned:,.0f} is tight vs monthly surplus ₹{avail:,.0f} "
            f"with active EMIs ₹{cash['active_emi_monthly']:,.0f}/mo."
        )

    return {
        "success": True,
        "festival_name": body.festival_name,
        "planned_budget": body.planned_budget,
        "days_remaining": days_rem,
        "monthly_saving_needed": round(monthly_needed, 2),
        "weekly_saving_needed": round(monthly_needed / 4.33, 2),
        "daily_saving_needed": round(monthly_needed / 30.0, 2),
        "emi_constraints": cash,
        "budget_feasible": feasible,
        "warning": warning,
        "suggested_budget_max": round(max(0.0, avail * max(months_rem, 0.25)), 2),
    }


class FestivalUpdateSavingsBody(BaseModel):
    festival_name: str = Field(..., min_length=1)
    amount_saved: float = Field(..., ge=0)
    festival_date: Optional[date] = None


def _linked_purchase_goals(conn, user_id: int, fest_name: str, fest_date: date) -> list[dict[str, Any]]:
    """Purchase goals linked to this festival (explicit key/label or fuzzy name/date)."""
    cur = conn.cursor()
    rows: list[tuple[Any, ...]] = []
    try:
        cur.execute(
            """
            SELECT id, item_name, target_amount, target_date, linked_festival_key, display_timeline_label
            FROM purchase_goals
            WHERE user_id = %s
              AND UPPER(COALESCE(status, '')) NOT IN ('CANCELLED', 'COMPLETED');
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    except Exception:
        conn.rollback()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, item_name, target_amount, target_date
            FROM purchase_goals
            WHERE user_id = %s
              AND UPPER(COALESCE(status, '')) NOT IN ('CANCELLED', 'COMPLETED');
            """,
            (user_id,),
        )
        rows = [(r[0], r[1], r[2], r[3], None, None) for r in cur.fetchall()]
    cur.close()

    fest_prefix = _norm_name(fest_name).replace(" ", "_").replace("-", "_")
    out: list[dict[str, Any]] = []
    for r in rows:
        gid, name, amt, td = int(r[0]), str(r[1]), float(r[2] or 0), r[3]
        fk = (str(r[4]) if len(r) > 4 and r[4] else "") or ""
        dl = (str(r[5]) if len(r) > 5 and r[5] else "") or ""
        td_d = td if isinstance(td, date) else datetime.strptime(str(td)[:10], "%Y-%m-%d").date()
        linked = False
        if fk and fest_prefix in _norm_name(fk).replace(" ", "_"):
            linked = True
        if dl and _match_db_name(fest_name, dl):
            linked = True
        if _match_db_name(fest_name, name):
            linked = True
        if abs((td_d - fest_date).days) <= 21:
            linked = True
        if linked:
            out.append(
                {
                    "goal_id": gid,
                    "item_name": name,
                    "target_amount": round(amt, 2),
                    "target_date": td_d.isoformat(),
                }
            )
    return out


@router.put("/{user_id}/update-savings")
def update_festival_savings(user_id: int, body: FestivalUpdateSavingsBody, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")

    fest_date = _resolve_festival_date(conn, user_id, body.festival_name, body.festival_date)

    row = _fetch_budget_row(conn, user_id, body.festival_name, fest_date)
    today = date.today()
    days_rem = max((fest_date - today).days, 0)
    months_rem = max(days_rem / 30.0, 0.25)

    if row:
        new_saved = float(row[3] or 0) + float(body.amount_saved)
        planned = float(row[2] or 0)
        last_year = float(row[1] or 0)
        income = _user_income(conn, user_id)
        recommended = planned if planned > 0 else round(last_year * 1.0526) if last_year > 0 else round(income * 0.08)
        gap = max(0.0, recommended - new_saved)
        monthly_needed = gap / months_rem if months_rem else 0.0
        cur.execute(
            """
            UPDATE festival_budgets
            SET saved_so_far = %s, monthly_target = %s, days_remaining = %s
            WHERE id = %s;
            """,
            (new_saved, monthly_needed, days_rem, row[0]),
        )
    else:
        income = _user_income(conn, user_id)
        recommended = round(income * 0.08)
        new_saved = float(body.amount_saved)
        gap = max(0.0, recommended - new_saved)
        monthly_needed = gap / months_rem if months_rem else 0.0
        cur.execute(
            """
            INSERT INTO festival_budgets (
              user_id, festival_name, festival_date, last_year_spent, planned_budget,
              saved_so_far, monthly_target, days_remaining, status, category_breakdown
            ) VALUES (%s, %s, %s, 0, 0, %s, %s, %s, 'UPCOMING', '{}'::jsonb);
            """,
            (user_id, body.festival_name.strip(), fest_date, new_saved, monthly_needed, days_rem),
        )
    cur.close()

    try:
        from services.financial_engine import recalculate_financial_state as _rfs

        _rfs(conn, user_id, "festival_savings_updated", None, f"Savings logged for {body.festival_name}.")
    except Exception:
        pass

    progress_pct = round(100.0 * new_saved / recommended, 1) if recommended > 0 else 0.0
    return {
        "success": True,
        "festival_name": body.festival_name,
        "saved_so_far": round(new_saved, 2),
        "recommended_budget": round(recommended, 2),
        "monthly_saving_needed": round(monthly_needed, 2),
        "progress_pct": progress_pct,
    }


@router.post("/{user_id}/events")
def create_planned_event(user_id: int, body: CreateEventBody, conn=Depends(get_db)) -> dict[str, Any]:
    cur = conn.cursor()
    cur.execute("SELECT name FROM users WHERE id = %s;", (user_id,))
    urow = cur.fetchone()
    if not urow:
        cur.close()
        raise HTTPException(404, "User not found")
    user_name = (urow[0] or "User").strip()
    cur.close()

    today = date.today()
    custom_horizon = _horizon_end(today, CUSTOM_EVENT_MAX_DAYS)
    if body.festival_date <= today:
        raise HTTPException(400, "Event date must be in the future.")
    if body.festival_date > custom_horizon:
        raise HTTPException(
            400,
            f"Event must be within the next {CUSTOM_EVENT_MAX_DAYS} days (~5 years).",
        )

    fest_name = body.festival_name.strip()
    fest_date = body.festival_date
    planned = float(body.planned_budget or 0)
    upsert_festival_budget_row(
        conn,
        user_id,
        fest_name,
        fest_date,
        planned_budget=planned,
        category_breakdown=body.category_budgets or {},
    )

    try:
        from services.financial_engine import recalculate_financial_state as _rfs

        _rfs(conn, user_id, "festival_event_created", None, f"Event plan added: {fest_name}.")
    except Exception:
        pass

    cal_d = _calendar_date_for_name(fest_name)
    is_custom = cal_d is None or cal_d != fest_date
    card = _build_festival_payload(
        conn,
        user_id,
        user_name,
        fest_name,
        fest_date,
        today,
        _user_income(conn, user_id),
        _food_delivery_monthly(conn, user_id),
        _subscription_monthly_total(conn, user_id),
        is_custom=is_custom,
        refresh_ai=True,
    )
    cash = monthly_surplus_snapshot(conn, user_id)
    return {"success": True, "event": card, "emi_constraints": cash}


@router.get("/{user_id}/events/{festival_name}/details")
def festival_event_details(
    user_id: int,
    festival_name: str,
    festival_date: Optional[str] = None,
    refresh: bool = True,
    conn=Depends(get_db),
) -> dict[str, Any]:
    cur = conn.cursor()
    cur.execute("SELECT name FROM users WHERE id = %s;", (user_id,))
    urow = cur.fetchone()
    if not urow:
        cur.close()
        raise HTTPException(404, "User not found")
    user_name = (urow[0] or "User").strip()
    cur.close()

    explicit: Optional[date] = None
    if festival_date:
        explicit = datetime.strptime(festival_date[:10], "%Y-%m-%d").date()
    fest_d = _resolve_festival_date(conn, user_id, festival_name, explicit)
    today = date.today()
    card = _build_festival_payload(
        conn,
        user_id,
        user_name,
        festival_name,
        fest_d,
        today,
        _user_income(conn, user_id),
        _food_delivery_monthly(conn, user_id),
        _subscription_monthly_total(conn, user_id),
        is_custom=_calendar_date_for_name(festival_name) is None or _calendar_date_for_name(festival_name) != fest_d,
        refresh_ai=refresh,
    )
    return {"event": card}


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
    horizon = _horizon_end(today)
    income = _user_income(conn, user_id)
    avg_saved = _avg_monthly_saved(conn, user_id)
    food_m = _food_delivery_monthly(conn, user_id)
    sub_m = _subscription_monthly_total(conn, user_id)

    upcoming: list[dict[str, Any]] = []
    total_budget = 0.0
    monthly_sum = 0.0

    for fest_name, fest_date, is_custom in _iter_upcoming_festival_slots(conn, user_id, today, horizon):
        card = _build_festival_payload(
            conn,
            user_id,
            user_name,
            fest_name,
            fest_date,
            today,
            income,
            food_m,
            sub_m,
            is_custom=is_custom,
            refresh_ai=True,
        )
        upcoming.append(card)
        total_budget += float(card["recommended_budget"])
        monthly_sum += float(card["monthly_saving_needed"])

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

    on_track = gap_month <= max(500, monthly_sum * 0.15) if monthly_sum > 0 else True
    cash = monthly_surplus_snapshot(conn, user_id)
    return {
        "upcoming_festivals": upcoming,
        "emi_constraints": cash,
        "total_festival_budget_needed": round(total_budget, 2),
        "months_to_save": round(max([x["months_remaining"] for x in upcoming] or [0]), 2),
        "monthly_total_target": round(monthly_sum, 2),
        "current_savings_rate_monthly": round(avg_saved, 2),
        "gap_vs_current_savings_monthly": round(gap_month, 2),
        "on_track": on_track,
        "gap_close_suggestions": gap_items,
        "biggest_festival": biggest,
        "next_festival": next_f,
    }
