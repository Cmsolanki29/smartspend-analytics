"""Big purchase planner — goals, EMI vs cash, sacrifice plan, Groq-backed English advice."""

from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_db
from services.ai_service import call_groq
from services.dashboard_scope import fetch_dashboard_mode, transaction_scope_sql
from services.emi_calculator import emi_vs_cash_from_loan

router = APIRouter(prefix="/purchases", tags=["Purchase Planner"])


def _refresh_health_score(conn, user_id: int) -> None:
    try:
        from services.scorer import refresh_user_health_score

        refresh_user_health_score(conn, user_id, invalidate_insights=True)
    except Exception:
        pass


def _months_between(a: date, b: date) -> int:
    if b <= a:
        return 1
    m = (b.year - a.year) * 12 + b.month - a.month
    if b.day < a.day:
        m -= 1
    return max(1, m)


def _add_months(d: date, months: int) -> date:
    m0 = d.month - 1 + months
    y = d.year + m0 // 12
    mo = m0 % 12 + 1
    last = monthrange(y, mo)[1]
    return date(y, mo, min(d.day, last))


def _best_buy_info(category: str, target_date: date) -> dict[str, Any]:
    c = (category or "OTHER").upper()
    if c == "APPLIANCE" and target_date.month in (4, 5, 6):
        return {
            "month": "March",
            "reason": "Pre-summer window — AC/fridge deals before peak demand",
            "discount_inr": 4000,
        }
    if c == "APPLIANCE":
        return {
            "month": "October 2026",
            "reason": "Diwali / festive sale — strong appliance discounts",
            "discount_inr": 5000,
        }
    if c == "VEHICLE":
        return {
            "month": "October 2026",
            "reason": "Navratri/Dussehra — two-wheeler promos common",
            "discount_inr": 5000,
        }
    if c == "ELECTRONICS":
        return {
            "month": "October–November 2026",
            "reason": "Diwali + Amazon Great Indian Festival / Flipkart Big Billion Days",
            "discount_inr": 15000,
        }
    return {
        "month": "January 2027",
        "reason": "New-year clearance on many categories",
        "discount_inr": 3000,
    }


def _emi_cash_payload(amount: float) -> dict[str, Any]:
    emi12_total = round(amount * 1.12, 2)
    emi24_total = round(amount * 1.18, 2)
    int12 = round(emi12_total - amount, 2)
    int24 = round(emi24_total - amount, 2)
    return {
        "cash": {
            "total": round(amount, 2),
            "monthly": None,
            "interest": 0,
            "verdict": f"BEST — avoid ~₹{int12:,.0f}+ interest vs typical 12m EMI",
        },
        "emi_12": {
            "total": emi12_total,
            "monthly": round(emi12_total / 12.0, 2),
            "interest": int12,
            "verdict": f"Costs about ₹{int12:,.0f} extra vs cash",
        },
        "emi_24": {
            "total": emi24_total,
            "monthly": round(emi24_total / 24.0, 2),
            "interest": int24,
            "verdict": f"Costs about ₹{int24:,.0f} extra vs cash",
        },
    }


def _top_category_spends(conn, user_id: int) -> list[tuple[str, float]]:
    cur = conn.cursor()
    mode = fetch_dashboard_mode(cur, user_id)
    scope = transaction_scope_sql("t", mode)
    cur.execute(
        f"""
        SELECT COALESCE(NULLIF(TRIM(t.category), ''), 'Other') AS c,
               SUM(t.amount)::float AS s
        FROM transactions t
        WHERE t.user_id = %s AND t.type = 'DEBIT'
          AND t.transaction_date >= CURRENT_DATE - INTERVAL '90 days'
          AND ({scope})
        GROUP BY 1
        ORDER BY s DESC
        LIMIT 6;
        """,
        (user_id,),
    )
    rows = [(r[0], float(r[1] or 0)) for r in cur.fetchall()]
    cur.close()
    return rows


def _build_sacrifice_plan(
    conn, user_id: int, monthly_gap: float, monthly_target: float
) -> list[dict[str, Any]]:
    if monthly_gap <= 0:
        return []
    cats = _top_category_spends(conn, user_id)
    if not cats:
        return []
    total = sum(s for _, s in cats) or 1.0
    plan: list[dict[str, Any]] = []
    remaining_gap = monthly_gap
    for cat, spend in cats:
        if remaining_gap <= 0:
            break
        share = spend / total
        suggested = min(spend * 0.35, remaining_gap * 0.55, spend * 0.9)
        suggested = round(suggested, 2)
        if suggested < 300:
            continue
        new_budget = max(0.0, round(spend - suggested, 2))
        months_earlier = (suggested / monthly_target) if monthly_target > 0 else 0
        impact = f"~{months_earlier:.1f} months faster toward goal" if months_earlier >= 0.1 else "Helps close monthly gap"
        plan.append(
            {
                "category": cat,
                "current_spend": round(spend, 2),
                "suggested_cut": suggested,
                "new_budget": new_budget,
                "impact": impact,
            }
        )
        remaining_gap -= suggested * 0.5
    return plan[:5]


def _avg_monthly_saved(conn, user_id: int) -> float:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(AVG(total_saved), 0)::float
        FROM (
          SELECT total_saved FROM monthly_summary
          WHERE user_id = %s
          ORDER BY year DESC, month DESC
          LIMIT 6
        ) t;
        """,
        (user_id,),
    )
    v = float(cur.fetchone()[0] or 0)
    cur.close()
    return v


def generate_purchase_advice(
    user_name: str,
    item_name: str,
    target_amount: float,
    months_remaining: int,
    monthly_target: float,
    current_savings_rate: float,
    best_buy_label: str,
) -> str:
    system = """You are SmartSpend financial advisor.
Give personalized purchase advice in clear English. Max 3 short sentences, 80 words total.
Be specific with rupee amounts. No JSON, no bullet labels, no generic platitudes."""

    prompt = (
        f"User: {user_name}\nWants: {item_name}\nCost: ₹{target_amount:,.0f}\n"
        f"Months to save: {months_remaining}\nNeed per month: ₹{monthly_target:,.0f}\n"
        f"Currently saving (avg/month): ₹{current_savings_rate:,.0f}\n"
        f"Best time to buy: {best_buy_label}\n"
        "Answer: (1) Is this realistic? one honest line. (2) One specific tip to save faster. "
        "(3) EMI vs cash — one line. (4) Short encouragement."
    )
    out = call_groq(system, prompt, max_tokens=180, temperature=0.5)
    text = out.strip() if isinstance(out, str) else ""
    if text:
        return text
    return (
        f"{user_name}, buying {item_name} for about ₹{target_amount:,.0f} in {months_remaining} months means saving "
        f"₹{monthly_target:,.0f} per month consistently. You currently average ₹{current_savings_rate:,.0f}/month saved—"
        f"close the gap by trimming discretionary spend. Prefer paying cash around {best_buy_label} to avoid EMI interest. "
        f"Steady discipline still makes this goal achievable."
    )


def _milestones(target_date: date, target_amount: float, monthly: float) -> list[dict[str, Any]]:
    labels = ["Month 1", "40% done!", "Halfway there!", "Almost there!", "BUY target"]
    out = []
    start = date.today()
    for i in range(1, 6):
        amt = min(target_amount, round(monthly * i, 2))
        dt = _add_months(start, i)
        if dt > target_date:
            dt = target_date
        out.append(
            {
                "month": dt.strftime("%B %Y"),
                "amount": amt,
                "label": labels[i - 1],
            }
        )
    return out


def _enrich_goal(conn, user_id: int, row: tuple) -> dict[str, Any]:
    (
        gid,
        item_name,
        target_amount,
        saved_amount,
        target_date,
        monthly_target_db,
        category,
        priority,
        status,
        best_buy_month,
        emi_json,
        _sac_json,
    ) = row
    today = date.today()
    td = target_date if isinstance(target_date, date) else datetime.strptime(str(target_date), "%Y-%m-%d").date()
    months_rem = _months_between(today, td)
    target_amount_f = float(target_amount or 0)
    saved_f = float(saved_amount or 0)
    remaining = max(0.0, target_amount_f - saved_f)
    monthly_target = remaining / months_rem if months_rem else remaining
    avg_saved = _avg_monthly_saved(conn, user_id)
    gap = max(0.0, monthly_target - avg_saved)
    binfo = _best_buy_info(category, td)
    effective = max(0.0, target_amount_f - binfo["discount_inr"])
    best_buy = {
        "month": binfo["month"],
        "reason": binfo["reason"],
        "effective_cost": round(effective, 2),
    }
    emi_vs = _emi_cash_payload(target_amount_f)
    if isinstance(emi_json, str) and emi_json:
        try:
            parsed = json.loads(emi_json)
            if isinstance(parsed, dict) and parsed.get("cash"):
                emi_vs = parsed
        except json.JSONDecodeError:
            pass
    sacrifice = _build_sacrifice_plan(conn, user_id, gap, monthly_target)

    cur = conn.cursor()
    cur.execute("SELECT name FROM users WHERE id = %s;", (user_id,))
    uname = (cur.fetchone() or ["User"])[0]
    cur.close()

    advice = generate_purchase_advice(
        str(uname).strip(),
        str(item_name),
        target_amount_f,
        months_rem,
        monthly_target,
        avg_saved,
        best_buy_month or best_buy["month"],
    )

    progress_pct = round(100.0 * saved_f / target_amount_f, 1) if target_amount_f > 0 else 0.0

    festival_link: Optional[dict[str, Any]] = None
    try:
        cur2 = conn.cursor()
        cur2.execute(
            "SELECT linked_festival_key, display_timeline_label FROM purchase_goals WHERE id = %s;",
            (gid,),
        )
        lk = cur2.fetchone()
        cur2.close()
        if lk:
            fk = (lk[0] or "").strip()
            dl = (lk[1] or "").strip()
            if fk or dl:
                label = dl or fk.replace("_", " ").title()
                festival_link = {"key": fk or None, "label": label}
    except Exception:
        pass

    return {
        "goal_id": gid,
        "item_name": item_name,
        "target_amount": target_amount_f,
        "target_date": td.isoformat(),
        "months_remaining": months_rem,
        "monthly_target": round(monthly_target, 2),
        "current_savings_rate": round(avg_saved, 2),
        "gap_per_month": round(gap, 2),
        "on_track": gap <= max(500, monthly_target * 0.15),
        "best_buy_month": best_buy,
        "emi_vs_cash": emi_vs,
        "sacrifice_plan": sacrifice,
        "ai_advice": advice,
        "progress_pct": progress_pct,
        "milestones": _milestones(td, target_amount_f, monthly_target),
        "category": category,
        "priority": priority,
        "status": status,
        "saved_amount": saved_f,
        "festival_link": festival_link,
    }


@router.get("/{user_id}")
def list_goals(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")
    cur.execute(
        """
        SELECT id, item_name, target_amount, saved_amount, target_date, monthly_target,
               category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan
        FROM purchase_goals
        WHERE user_id = %s
          AND UPPER(COALESCE(status, '')) NOT IN ('CANCELLED', 'COMPLETED')
        ORDER BY
          CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
          target_date;
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    goals = [_enrich_goal(conn, user_id, r) for r in rows]
    total_monthly = sum(g["monthly_target"] for g in goals)
    avg_saved = _avg_monthly_saved(conn, user_id)
    on_track_count = sum(1 for g in goals if g.get("on_track"))
    return {
        "goals": goals,
        "goals_on_track": on_track_count,
        "goals_total": len(goals),
        "total_monthly_saving_needed": round(total_monthly, 2),
        "current_savings_rate_monthly": round(avg_saved, 2),
        "gap_monthly": round(max(0.0, total_monthly - avg_saved), 2),
    }


class AddGoalBody(BaseModel):
    item_name: str = Field(..., min_length=1)
    target_amount: float = Field(..., gt=0)
    target_date: str
    category: str = Field(default="OTHER", max_length=50)
    priority: str = Field(default="MEDIUM")
    down_payment: float = Field(default=0, ge=0)
    annual_interest_rate_pct: Optional[float] = Field(default=None, ge=0, le=60)
    emi_tenure_months: Optional[int] = Field(default=None, ge=1, le=360)
    linked_festival_key: Optional[str] = Field(default=None, max_length=80)
    display_timeline_label: Optional[str] = Field(default=None, max_length=80)


@router.post("/{user_id}/add-goal")
def add_goal(user_id: int, body: AddGoalBody, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")
    try:
        td = datetime.strptime(body.target_date[:10], "%Y-%m-%d").date()
    except ValueError:
        cur.close()
        raise HTTPException(400, "target_date must be YYYY-MM-DD")

    today = date.today()
    months_rem = _months_between(today, td)
    saved_initial = max(0.0, min(float(body.down_payment or 0), float(body.target_amount)))
    remaining = max(0.0, float(body.target_amount) - saved_initial)
    monthly_target = remaining / months_rem if months_rem else remaining
    binfo = _best_buy_info(body.category, td)
    best_buy_str = f"{binfo['month']} — {binfo['reason']}"
    amount_f = float(body.target_amount)
    down = max(0.0, min(float(body.down_payment or 0), amount_f))
    if body.emi_tenure_months and body.annual_interest_rate_pct is not None:
        emi_payload = emi_vs_cash_from_loan(
            amount_f,
            float(body.annual_interest_rate_pct),
            int(body.emi_tenure_months),
            down,
        )
    else:
        emi_payload = _emi_cash_payload(amount_f)
    emi_vs = json.dumps(emi_payload)
    sacrifice = json.dumps(_build_sacrifice_plan(conn, user_id, max(0, monthly_target - _avg_monthly_saved(conn, user_id)), monthly_target))

    fk = (body.linked_festival_key or "").strip() or None
    dl = (body.display_timeline_label or "").strip() or None

    insert_cols = (
        "user_id, item_name, target_amount, saved_amount, target_date, monthly_target, "
        "category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan"
    )
    insert_vals = (
        user_id,
        body.item_name.strip(),
        amount_f,
        round(saved_initial, 2),
        td,
        round(monthly_target, 2),
        body.category.upper()[:50],
        body.priority.upper()[:10],
        "SAVING",
        best_buy_str[:200],
        emi_vs,
        sacrifice,
    )
    try:
        cur.execute(
            f"""
            INSERT INTO purchase_goals (
              {insert_cols}, linked_festival_key, display_timeline_label
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            RETURNING id, item_name, target_amount, saved_amount, target_date, monthly_target,
                      category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan;
            """,
            insert_vals + (fk, dl),
        )
    except Exception:
        conn.rollback()
        cur = conn.cursor()
        cur.execute(
            f"""
            INSERT INTO purchase_goals ({insert_cols})
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            RETURNING id, item_name, target_amount, saved_amount, target_date, monthly_target,
                      category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan;
            """,
            insert_vals,
        )
    row = cur.fetchone()
    goal_id_new = row[0] if row else None
    cur.close()
    if fk or dl:
        try:
            from routes.festival_predictor import upsert_festival_budget_row

            label = (dl or body.item_name).strip()
            upsert_festival_budget_row(
                conn,
                user_id,
                label,
                td,
                planned_budget=amount_f,
                saved_so_far=saved_initial,
            )
        except Exception:
            pass
    result = _enrich_goal(conn, user_id, row)
    # Fire cascade recalculation
    try:
        from services.financial_engine import recalculate_financial_state
        recalculate_financial_state(conn, user_id, "purchase_goal_added", goal_id_new,
                                    f"Purchase goal '{body.item_name}' added. Monthly pace: ₹{round(monthly_target,0):,.0f}/mo.")
    except Exception:
        pass
    _refresh_health_score(conn, user_id)
    return result


class UpdateSavingsBody(BaseModel):
    amount_saved: float = Field(..., ge=0)


@router.put("/{user_id}/{goal_id}/update-savings")
def update_savings(user_id: int, goal_id: int, body: UpdateSavingsBody, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, item_name, target_amount, saved_amount, target_date, monthly_target,
               category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan
        FROM purchase_goals
        WHERE id = %s AND user_id = %s AND status <> 'CANCELLED';
        """,
        (goal_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        raise HTTPException(404, "Goal not found")
    new_saved = float(row[3] or 0) + float(body.amount_saved)
    st = "COMPLETED" if new_saved >= float(row[2] or 0) else row[8]
    cur.execute(
        "UPDATE purchase_goals SET saved_amount = %s, status = %s WHERE id = %s;",
        (new_saved, st, goal_id),
    )
    cur.execute(
        """
        SELECT id, item_name, target_amount, saved_amount, target_date, monthly_target,
               category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan
        FROM purchase_goals WHERE id = %s;
        """,
        (goal_id,),
    )
    row2 = cur.fetchone()
    cur.close()
    try:
        from services.financial_engine import recalculate_financial_state

        recalculate_financial_state(
            conn,
            user_id,
            trigger_type="purchase_savings_update",
            trigger_id=goal_id,
            trigger_summary="Purchase goal savings updated",
        )
        conn.commit()
    except Exception:
        pass
    _refresh_health_score(conn, user_id)
    return _enrich_goal(conn, user_id, row2)


class PostponeGoalBody(BaseModel):
    new_target_date: str = Field(..., min_length=8, max_length=12)
    reason: str = Field(default="", max_length=500)
    festival_key: Optional[str] = Field(default=None, max_length=50)
    display_timeline_label: Optional[str] = Field(default=None, max_length=80)


class PostponeMonthsBody(BaseModel):
    postpone_months: int = Field(..., ge=1, le=60)


@router.post("/{user_id}/{goal_id}/postpone")
def postpone_goal_by_months(user_id: int, goal_id: int, body: PostponeMonthsBody, conn=Depends(get_db)):
    """
    Shift goal target_date forward by N months; recompute monthly_target from remaining balance.

    curl -s -X POST http://127.0.0.1:8001/api/purchases/1/2/postpone \\
      -H "Content-Type: application/json" -d "{\\"postpone_months\\": 3}"
    """
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")

    cur.execute(
        """
        SELECT id, item_name, target_amount, saved_amount, target_date, monthly_target,
               category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan
        FROM purchase_goals
        WHERE id = %s AND user_id = %s AND UPPER(COALESCE(status, '')) <> 'CANCELLED';
        """,
        (goal_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        raise HTTPException(404, "Goal not found")

    old_td = row[4] if isinstance(row[4], date) else datetime.strptime(str(row[4])[:10], "%Y-%m-%d").date()
    target_amount_f = float(row[2] or 0)
    saved_f = float(row[3] or 0)
    remaining = max(0.0, target_amount_f - saved_f)
    new_td = _add_months(old_td, body.postpone_months)
    if new_td <= old_td:
        cur.close()
        raise HTTPException(400, "postpone_months must move target_date forward")

    today = date.today()
    months_rem = max(1, _months_between(today, new_td))
    monthly_target = round(remaining / months_rem, 2)
    emi_vs = json.dumps(_emi_cash_payload(target_amount_f))
    gap = max(0.0, monthly_target - _avg_monthly_saved(conn, user_id))
    sacrifice = json.dumps(_build_sacrifice_plan(conn, user_id, gap, monthly_target))

    row2 = None
    try:
        cur.execute(
            """
            UPDATE purchase_goals
            SET original_target_date = COALESCE(original_target_date, %s),
                target_date = %s,
                monthly_target = %s,
                emi_vs_cash = %s::jsonb,
                sacrifice_plan = %s::jsonb
            WHERE id = %s AND user_id = %s
            RETURNING id, item_name, target_amount, saved_amount, target_date, monthly_target,
                      category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan;
            """,
            (old_td, new_td, monthly_target, emi_vs, sacrifice, goal_id, user_id),
        )
        row2 = cur.fetchone()
    except Exception as exc:
        err = str(exc).lower()
        if "original_target_date" not in err and "undefinedcolumn" not in err.replace(" ", ""):
            cur.close()
            raise HTTPException(500, f"postpone failed: {exc}") from exc
        conn.rollback()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE purchase_goals
            SET target_date = %s, monthly_target = %s,
                emi_vs_cash = %s::jsonb, sacrifice_plan = %s::jsonb
            WHERE id = %s AND user_id = %s
            RETURNING id, item_name, target_amount, saved_amount, target_date, monthly_target,
                      category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan;
            """,
            (new_td, monthly_target, emi_vs, sacrifice, goal_id, user_id),
        )
        row2 = cur.fetchone()

    if not row2:
        cur.close()
        raise HTTPException(500, "postpone update returned no row")

    try:
        cur.execute("SAVEPOINT postpone_finlog2")
        cur.execute(
            """
            INSERT INTO financial_advice (
                user_id, advice_type, title, description, action_items, severity, user_action, executed_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, NOW());
            """,
            (
                user_id,
                "postpone_accepted",
                "Purchase goal postponed (months)",
                f"Postponed by {body.postpone_months} months from EMI Tracker.",
                json.dumps(
                    {
                        "goal_id": goal_id,
                        "postpone_months": body.postpone_months,
                        "new_target_date": new_td.isoformat(),
                        "prior_target_date": old_td.isoformat(),
                    }
                ),
                "info",
                "accepted",
            ),
        )
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT postpone_finlog2")
        except Exception:
            conn.rollback()
            cur.close()
            cur = conn.cursor()

    # Fire cascade recalculation
    try:
        from services.financial_engine import recalculate_financial_state as _rfs
        _rfs(conn, user_id, 'purchase_goal_postponed', goal_id, 'Goal postponed.')
    except Exception:
        pass
    cur.close()
    enriched = _enrich_goal(conn, user_id, row2)
    _refresh_health_score(conn, user_id)
    return {
        "success": True,
        "message": f"Goal “{enriched.get('item_name', '')}” moved by {body.postpone_months} month(s) to {new_td.isoformat()}.",
        "goal": enriched,
        "previous_target_date": old_td.isoformat(),
    }


@router.post("/{user_id}/goals/{goal_id}/postpone")
def postpone_purchase_goal(user_id: int, goal_id: int, body: PostponeGoalBody, conn=Depends(get_db)):
    """Move a goal's target date (EMI Tracker festival shift or generic date) and refresh monthly savings pace."""
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")
    try:
        new_td = datetime.strptime(body.new_target_date[:10], "%Y-%m-%d").date()
    except ValueError:
        cur.close()
        raise HTTPException(400, "new_target_date must be YYYY-MM-DD")
    if new_td <= date.today():
        cur.close()
        raise HTTPException(400, "new_target_date must be in the future")

    cur.execute(
        """
        SELECT id, item_name, target_amount, saved_amount, target_date, monthly_target,
               category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan
        FROM purchase_goals
        WHERE id = %s AND user_id = %s AND UPPER(COALESCE(status, '')) <> 'CANCELLED';
        """,
        (goal_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        raise HTTPException(404, "Goal not found")

    old_td = row[4] if isinstance(row[4], date) else datetime.strptime(str(row[4])[:10], "%Y-%m-%d").date()
    if new_td <= old_td:
        cur.close()
        raise HTTPException(400, "new_target_date must be after the goal's current target_date")

    target_amount_f = float(row[2] or 0)
    saved_f = float(row[3] or 0)
    remaining = max(0.0, target_amount_f - saved_f)
    today = date.today()
    months_rem = max(1, _months_between(today, new_td))
    mt = round(remaining / months_rem, 2)

    emi_vs = json.dumps(_emi_cash_payload(target_amount_f))
    gap = max(0.0, mt - _avg_monthly_saved(conn, user_id))
    sacrifice = json.dumps(_build_sacrifice_plan(conn, user_id, gap, mt))

    fk = (body.festival_key or "").strip()[:50] or None
    dl = (body.display_timeline_label or "").strip()[:80] or None

    row2 = None
    try:
        cur.execute(
            """
            UPDATE purchase_goals
            SET original_target_date = COALESCE(original_target_date, %s),
                target_date = %s,
                monthly_target = %s,
                emi_vs_cash = %s::jsonb,
                sacrifice_plan = %s::jsonb,
                linked_festival_key = %s,
                display_timeline_label = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, item_name, target_amount, saved_amount, target_date, monthly_target,
                      category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan;
            """,
            (old_td, new_td, mt, emi_vs, sacrifice, fk, dl, goal_id, user_id),
        )
        row2 = cur.fetchone()
    except Exception as exc:
        err = str(exc).lower()
        if "linked_festival" not in err and "display_timeline" not in err and "undefinedcolumn" not in err.replace(" ", ""):
            cur.close()
            raise HTTPException(500, f"postpone update failed: {exc}") from exc
        conn.rollback()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE purchase_goals
            SET original_target_date = COALESCE(original_target_date, %s),
                target_date = %s,
                monthly_target = %s,
                emi_vs_cash = %s::jsonb,
                sacrifice_plan = %s::jsonb
            WHERE id = %s AND user_id = %s
            RETURNING id, item_name, target_amount, saved_amount, target_date, monthly_target,
                      category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan;
            """,
            (old_td, new_td, mt, emi_vs, sacrifice, goal_id, user_id),
        )
        row2 = cur.fetchone()
    if not row2:
        cur.close()
        raise HTTPException(500, "postpone update returned no row")

    try:
        cur.execute("SAVEPOINT postpone_finlog")
        cur.execute(
            """
            INSERT INTO financial_advice (
                user_id, advice_type, title, description, action_items, severity, user_action, executed_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, NOW());
            """,
            (
                user_id,
                "postpone_accepted",
                "Purchase goal postponed from EMI Tracker",
                body.reason or "User postponed goal to improve EMI affordability.",
                json.dumps(
                    {
                        "goal_id": goal_id,
                        "new_target_date": new_td.isoformat(),
                        "prior_target_date": old_td.isoformat(),
                        "festival_key": fk,
                        "display_timeline_label": dl,
                    }
                ),
                "info",
                "accepted",
            ),
        )
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT postpone_finlog")
        except Exception:
            conn.rollback()
            cur.close()
            cur = conn.cursor()

    try:
        from services.financial_engine import recalculate_financial_state as _rfs

        _rfs(conn, user_id, "purchase_goal_postponed", goal_id, "Goal postponed to festival milestone.")
    except Exception:
        pass
    cur.close()
    enriched = _enrich_goal(conn, user_id, row2)
    _refresh_health_score(conn, user_id)
    return {
        "success": True,
        "message": f"Goal “{enriched.get('item_name', '')}” target moved to {new_td.isoformat()}.",
        "goal": enriched,
        "previous_target_date": old_td.isoformat(),
    }


def _complete_goal_impl(user_id: int, goal_id: int, conn) -> dict[str, Any]:
    """Mark a purchase goal done — removes it from the active planner list."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, item_name, target_amount, saved_amount, target_date, monthly_target,
               category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan
        FROM purchase_goals
        WHERE id = %s AND user_id = %s
          AND UPPER(COALESCE(status, '')) NOT IN ('CANCELLED', 'COMPLETED');
        """,
        (goal_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        raise HTTPException(404, "Goal not found")
    target_f = float(row[2] or 0)
    saved_f = float(row[3] or 0)
    final_saved = max(saved_f, target_f) if target_f > 0 else saved_f
    cur.execute(
        """
        UPDATE purchase_goals
        SET status = 'COMPLETED', saved_amount = %s
        WHERE id = %s AND user_id = %s
        RETURNING id, item_name, target_amount, saved_amount, target_date, monthly_target,
                  category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan;
        """,
        (final_saved, goal_id, user_id),
    )
    row2 = cur.fetchone()
    conn.commit()
    cur.close()
    try:
        from services.financial_engine import recalculate_financial_state

        recalculate_financial_state(
            conn,
            user_id,
            trigger_type="purchase_goal_completed",
            trigger_id=goal_id,
            trigger_summary=f"Purchase goal '{row[1]}' marked complete.",
        )
        conn.commit()
    except Exception:
        pass
    _refresh_health_score(conn, user_id)
    return {
        "success": True,
        "status": "COMPLETED",
        "message": f"Goal “{row[1]}” marked complete.",
        "goal": _enrich_goal(conn, user_id, row2) if row2 else None,
    }


@router.post("/{user_id}/{goal_id}/complete")
def complete_goal(user_id: int, goal_id: int, conn=Depends(get_db)):
    return _complete_goal_impl(user_id, goal_id, conn)


@router.post("/{user_id}/goals/{goal_id}/complete")
def complete_goal_nested(user_id: int, goal_id: int, conn=Depends(get_db)):
    """Alias path (matches postpone URL style) for older frontends / proxies."""
    return _complete_goal_impl(user_id, goal_id, conn)


@router.delete("/{user_id}/{goal_id}")
def cancel_goal(user_id: int, goal_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute(
        "UPDATE purchase_goals SET status = 'CANCELLED' WHERE id = %s AND user_id = %s RETURNING id;",
        (goal_id, user_id),
    )
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "Goal not found")
    cur.close()
    try:
        from services.financial_engine import recalculate_financial_state

        recalculate_financial_state(conn, user_id, "purchase_goal_cancelled", goal_id)
    except Exception:
        pass
    _refresh_health_score(conn, user_id)
    return {"success": True, "status": "CANCELLED"}
