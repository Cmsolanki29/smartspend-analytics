"""Deterministic EMI + goals + liquidity affordability (CA-style). Mounted under /emi."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_db
from routes.emi_detector import _build_emi_detection
from services.dashboard_scope import fetch_dashboard_mode, transaction_scope_sql
from routes.festival_predictor import INDIAN_FESTIVALS_2026, _match_db_name
from routes.purchase_planner import _add_months, _months_between

router = APIRouter(prefix="/emi", tags=["EMI Tracker"])

_EPS = 1e-6


def _parse_date(d: Any) -> date:
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def _baseline_buffer(conn, user_id: int) -> float:
    """
    Living / essential buffer (B) for liquidity_floor.

    Policy: use `users.monthly_fixed_expenses` when present and > 0.
    Otherwise estimate from last 90 days of DEBIT transactions excluding obvious
    EMI/loan merchants (simple keyword filter). Clamp to [2000, 12000].
    If fewer than 5 qualifying debits, fall back to ₹2,000.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COALESCE(monthly_fixed_expenses, 0)::float
            FROM users WHERE id = %s;
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row and float(row[0] or 0) > 0:
            return round(float(row[0]), 2)
    except Exception:
        conn.rollback()
    finally:
        try:
            cur.close()
        except Exception:
            pass

    cur = conn.cursor()
    try:
        mode = fetch_dashboard_mode(cur, user_id)
        scope = transaction_scope_sql("t", mode)
        cur.execute(
            f"""
            SELECT COALESCE(SUM(t.amount), 0)::float, COUNT(*)::int
            FROM transactions t
            WHERE t.user_id = %s
              AND t.type = 'DEBIT'
              AND t.transaction_date >= CURRENT_DATE - INTERVAL '90 days'
              AND LOWER(COALESCE(t.merchant, '') || ' ' || COALESCE(t.description, '')) NOT LIKE '%%emi%%'
              AND LOWER(COALESCE(t.merchant, '') || ' ' || COALESCE(t.description, '')) NOT LIKE '%%loan%%'
              AND LOWER(COALESCE(t.merchant, '') || ' ' || COALESCE(t.description, '')) NOT LIKE '%%nach%%'
              AND LOWER(COALESCE(t.merchant, '') || ' ' || COALESCE(t.description, '')) NOT LIKE '%%ecs%%'
              AND ({scope});
            """,
            (user_id,),
        )
        total, cnt = cur.fetchone()
        total_f = float(total or 0)
        cnt_i = int(cnt or 0)
        if cnt_i < 5:
            return 2000.0
        monthly_est = total_f / 3.0
        est = monthly_est * 0.12
        return round(max(2000.0, min(12000.0, est)), 2)
    except Exception:
        return 2000.0
    finally:
        cur.close()


def _load_goals_for_affordability(cur, user_id: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, item_name, COALESCE(target_amount, 0)::float, COALESCE(saved_amount, 0)::float,
               target_date, COALESCE(monthly_target, 0)::float, COALESCE(category, 'OTHER'),
               COALESCE(priority, 'MEDIUM'), COALESCE(status, 'SAVING')
        FROM purchase_goals
        WHERE user_id = %s
          AND UPPER(COALESCE(status, '')) NOT IN ('CANCELLED', 'COMPLETED');
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        td = _parse_date(r[4])
        out.append(
            {
                "goal_id": int(r[0]),
                "item_name": str(r[1]),
                "target_amount": float(r[2] or 0),
                "saved_amount": float(r[3] or 0),
                "target_date": td,
                "monthly_target": float(r[5] or 0),
                "category": str(r[6] or "OTHER").upper(),
                "priority": str(r[7] or "MEDIUM").upper(),
                "status": str(r[8] or ""),
            }
        )
    return out


def _important_days_between(conn, user_id: int, start: date, end: date) -> list[dict[str, Any]]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT title, event_date, COALESCE(notes, '')
            FROM user_important_days
            WHERE user_id = %s
              AND event_date >= %s
              AND event_date <= %s
            ORDER BY event_date;
            """,
            (user_id, start, end),
        )
        rows = cur.fetchall()
    except Exception:
        conn.rollback()
        return []
    finally:
        cur.close()
    return [{"title": str(a), "event_date": b, "notes": str(c or "")} for a, b, c in rows]


def _next_festival_chip(conn, user_id: int, before: date) -> Optional[dict[str, str]]:
    """Next calendar festival before `before` (for UI chip when no goal-specific link)."""
    today = date.today()
    best: Optional[tuple[date, str]] = None
    for fest in INDIAN_FESTIVALS_2026:
        d = datetime.strptime(fest["date"], "%Y-%m-%d").date()
        if today < d <= before:
            if best is None or d < best[0]:
                best = (d, fest["name"])
    if best:
        return {"name": best[1], "date": best[0].isoformat()}
    return None


def _linked_festival_for_goal(
    conn, user_id: int, item_name: str, goal_target: date
) -> Optional[dict[str, str]]:
    today = date.today()
    item_l = (item_name or "").lower()
    tokens = [t for t in re.split(r"[^\w]+", item_l) if len(t) >= 3]

    for fest in INDIAN_FESTIVALS_2026:
        d = datetime.strptime(fest["date"], "%Y-%m-%d").date()
        if not (today < d <= goal_target):
            continue
        fn = fest["name"].lower()
        if any(t in fn for t in tokens) or any(tok in item_l for tok in fn.split()):
            return {"name": fest["name"], "date": d.isoformat()}

    for row in _important_days_between(conn, user_id, today, goal_target):
        ed = row["event_date"]
        if isinstance(ed, date):
            ed_d = ed
        else:
            ed_d = _parse_date(ed)
        blob = f"{row['title']} {row['notes']}".lower()
        if any(t in blob for t in tokens) or any(t in item_l for t in blob.split() if len(t) > 3):
            return {"name": row["title"][:80], "date": ed_d.isoformat()}

    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT festival_name, festival_date
            FROM festival_budgets
            WHERE user_id = %s
              AND festival_date > %s
              AND festival_date <= %s
            ORDER BY festival_date
            LIMIT 3;
            """,
            (user_id, today, goal_target),
        )
        for fn, fd in cur.fetchall():
            if fd and _match_db_name(str(fn), item_name):
                return {"name": str(fn), "date": fd.isoformat() if hasattr(fd, "isoformat") else str(fd)}
    except Exception:
        conn.rollback()
    finally:
        cur.close()

    return _next_festival_chip(conn, user_id, goal_target)


def _defer_sort_key(g: dict[str, Any]) -> tuple[int, int, date, float]:
    cat = (g.get("category") or "OTHER").upper()
    pref = 0 if cat in ("VEHICLE", "ELECTRONICS", "APPLIANCE") else 1
    pr = (g.get("priority") or "MEDIUM").upper()
    pri = 0 if pr == "LOW" else (1 if pr == "MEDIUM" else 2)
    return (pref, pri, g["target_date"], -float(g.get("monthly_target") or 0))


def _festivals_calendar_static() -> list[dict[str, Any]]:
    """
    Deterministic festival milestones (calendar dates) for the next ~18 months.
    Navratri uses **start** day; Dussehra = Vijayadashami. Used when suggesting purchase
    goal shifts (EMI affordability) — independent of user timezone; dates are plain dates.
    """
    raw: list[tuple[str, str, date]] = [
        ("MAKAR_SANKRANTI_2026", "Makar Sankranti", date(2026, 1, 14)),
        ("HOLI_2026", "Holi", date(2026, 3, 29)),
        ("GANESH_CHATURTHI_2026", "Ganesh Chaturthi", date(2026, 9, 14)),
        ("NAVRATRI_2026", "Navratri", date(2026, 10, 2)),
        ("DUSSEHRA_2026", "Dussehra (Vijayadashami)", date(2026, 10, 11)),
        ("DIWALI_2026", "Diwali", date(2026, 10, 20)),
        ("MAKAR_SANKRANTI_2027", "Makar Sankranti", date(2027, 1, 14)),
        ("HOLI_2027", "Holi", date(2027, 3, 19)),
        ("GANESH_CHATURTHI_2027", "Ganesh Chaturthi", date(2027, 9, 3)),
        ("NAVRATRI_2027", "Navratri", date(2027, 9, 22)),
        ("DUSSEHRA_2027", "Dussehra (Vijayadashami)", date(2027, 10, 1)),
        ("DIWALI_2027", "Diwali", date(2027, 10, 20)),
    ]
    out: list[dict[str, Any]] = []
    for key, name, d in raw:
        out.append(
            {
                "key": key,
                "name": name,
                "suggested_target_date": d.isoformat(),
                "window_start": (d - timedelta(days=3)).isoformat(),
                "window_end": (d + timedelta(days=3)).isoformat(),
            }
        )
    return sorted(out, key=lambda x: x["suggested_target_date"])


def _next_festival_milestones_after(goal_td: date, milestones: list[dict[str, Any]], take: int = 2) -> list[dict[str, Any]]:
    """Next ``take`` milestones strictly **after** ``goal_td`` (push-later semantics)."""
    res: list[dict[str, Any]] = []
    for m in milestones:
        sd = datetime.strptime(str(m["suggested_target_date"])[:10], "%Y-%m-%d").date()
        if sd > goal_td:
            res.append(m)
            if len(res) >= take:
                break
    return res


def _compute_generic_postpone(
    goal_td: date, remaining: float, old_m: float, shortfall: float, today: date
) -> tuple[Optional[int], Optional[date], float, float]:
    best_n: Optional[int] = None
    best_new_td: Optional[date] = None
    best_new_m = 0.0
    for n in range(1, 61):
        new_td = _add_months(goal_td, n)
        months_new = max(1, _months_between(today, new_td))
        new_m = remaining / months_new if months_new else old_m
        freed_m = old_m - new_m
        if freed_m + _EPS >= shortfall:
            best_n = n
            best_new_td = new_td
            best_new_m = new_m
            break
    freed = round(old_m - best_new_m, 2) if best_n is not None and best_new_td is not None else 0.0
    return best_n, best_new_td, best_new_m, freed


def _default_goal_id_for_defer(entries: list[dict[str, Any]]) -> Optional[int]:
    """
    Prefer a goal that can close the EMI shortfall; among those pick LOW then MEDIUM then HIGH,
    then **smallest** ``monthly_target``. Never prefer HIGH when any MEDIUM/LOW entry can close.
    """
    if not entries:
        return None
    closers = [e for e in entries if e.get("can_close_shortfall")]
    pool = closers if closers else entries

    def pr_rank(p: str) -> int:
        u = (p or "MEDIUM").upper()
        return 0 if u == "LOW" else (1 if u == "MEDIUM" else 2)

    med_low = [e for e in pool if (e.get("priority") or "").upper() != "HIGH"]
    use = med_low if med_low else pool
    use = sorted(use, key=lambda e: (pr_rank(str(e.get("priority"))), float(e.get("monthly_target") or 0)))
    return int(use[0]["goal_id"]) if use else None


def _defer_entry_for_goal(
    conn: Any,
    user_id: int,
    cand: dict[str, Any],
    shortfall: float,
    today: date,
    milestones: list[dict[str, Any]],
    is_last_resort: bool,
) -> Optional[dict[str, Any]]:
    goal_td = cand["target_date"]
    remaining = max(0.0, float(cand["target_amount"]) - float(cand["saved_amount"]))
    old_m = float(cand["monthly_target"] or 0)

    best_n, best_new_td, best_new_m, generic_freed = _compute_generic_postpone(
        goal_td, remaining, old_m, shortfall, today
    )

    fest_hits = _next_festival_milestones_after(goal_td, milestones, 2)
    postpone_options: list[dict[str, Any]] = []
    for i, fm in enumerate(fest_hits[:2]):
        new_td = datetime.strptime(str(fm["suggested_target_date"])[:10], "%Y-%m-%d").date()
        months_new = max(1, _months_between(today, new_td))
        new_m = remaining / months_new if months_new else old_m
        freed_m = round(old_m - new_m, 2)
        postpone_options.append(
            {
                "option_id": "A" if i == 0 else "B",
                "label": f'Move {cand["item_name"]} to {fm["name"]} ({new_td.strftime("%d %b %Y")})',
                "festival_key": fm["key"],
                "new_target_date": new_td.isoformat(),
                "projected_monthly_target": round(new_m, 2),
                "freed_monthly": freed_m,
                "closes_shortfall": bool(freed_m + _EPS >= shortfall),
                "display_timeline_label": f'{fm["name"]} {new_td.year}',
            }
        )

    can_close = bool(
        (best_n is not None and best_new_td is not None and generic_freed + _EPS >= shortfall)
        or any(o["closes_shortfall"] for o in postpone_options)
    )

    if best_n is None and not postpone_options:
        return None

    linked = _linked_festival_for_goal(conn, user_id, cand["item_name"], goal_td)
    entry: dict[str, Any] = {
        "goal_id": int(cand["goal_id"]),
        "item_name": cand["item_name"],
        "current_target_date": goal_td.isoformat(),
        "monthly_target": round(old_m, 2),
        "priority": str(cand.get("priority") or "MEDIUM").upper(),
        "postpone_options": postpone_options,
        "generic_postpone_months": best_n,
        "generic_new_target_date": best_new_td.isoformat() if best_new_td else None,
        "generic_new_monthly_target": round(best_new_m, 2) if best_n is not None else None,
        "generic_freed_monthly": generic_freed if best_n is not None else None,
        "can_close_shortfall": can_close,
        "is_last_resort": is_last_resort,
        "linked_festival": linked,
    }
    return entry


def _postpone_months_to_reach(goal_td: date, target_td: date) -> int:
    """Smallest n in 1..60 with _add_months(goal_td, n) >= target_td (legacy postpone-by-months)."""
    for n in range(1, 61):
        if _add_months(goal_td, n) >= target_td:
            return n
    return 60


def _compose_emi_suggestion_object(
    defer_entries: list[dict[str, Any]],
    default_id: Optional[int],
    shortfall: float,
    P: float,
    rationale_lines: list[str],
) -> dict[str, Any]:
    did = default_id if default_id is not None else int(defer_entries[0]["goal_id"])
    def_row = next((e for e in defer_entries if e["goal_id"] == did), defer_entries[0])
    postpone_options = list(def_row.get("postpone_options") or [])
    gen_m = def_row.get("generic_postpone_months")
    gen_td_s = def_row.get("generic_new_target_date")
    gen_new_m = float(def_row.get("generic_new_monthly_target") or 0)
    old_m = float(def_row["monthly_target"])
    goal_td = datetime.strptime(str(def_row["current_target_date"])[:10], "%Y-%m-%d").date()

    if gen_m is not None and gen_td_s:
        legacy_suggested = gen_td_s
        legacy_new_m = gen_new_m
        legacy_postpone = int(gen_m)
        freed_default = round(float(def_row.get("generic_freed_monthly") or (old_m - gen_new_m)), 2)
    elif postpone_options:
        legacy_suggested = postpone_options[0]["new_target_date"]
        legacy_new_m = float(postpone_options[0]["projected_monthly_target"])
        fest_td = datetime.strptime(legacy_suggested[:10], "%Y-%m-%d").date()
        legacy_postpone = _postpone_months_to_reach(goal_td, fest_td)
        freed_default = round(old_m - legacy_new_m, 2)
    else:
        legacy_suggested = goal_td.isoformat()
        legacy_new_m = old_m
        legacy_postpone = 1
        freed_default = 0.0

    linked = def_row.get("linked_festival")

    primary_body = (
        f"Gap vs safe headroom / liquidity: about Rs.{shortfall:,.0f}/mo on a Rs.{P:,.0f}/mo new EMI. "
        f'Shifting "{def_row["item_name"]}" to a later milestone lowers the monthly pace you must save.'
    )
    if def_row.get("is_last_resort"):
        primary_body = (
            f"Gap: about Rs.{shortfall:,.0f}/mo on Rs.{P:,.0f}/mo new EMI. Only HIGH-priority goals can be moved—"
            f'confirm consciously before shifting "{def_row["item_name"]}".'
        )

    return {
        "primary_title": "You can still take this EMI if you move a purchase plan",
        "primary_body": primary_body,
        "deferrable_goals": defer_entries,
        "default_goal_id": default_id,
        "postpone_options": postpone_options,
        "generic_postpone_months": gen_m,
        "goal_id": int(def_row["goal_id"]),
        "item_name": def_row["item_name"],
        "current_target_date": def_row["current_target_date"],
        "suggested_target_date": legacy_suggested,
        "postpone_months": legacy_postpone,
        "old_monthly_target": round(old_m, 2),
        "new_monthly_target": round(float(legacy_new_m), 2),
        "freed_monthly": freed_default,
        "linked_festival": linked,
        "message": (
            f'Move "{def_row["item_name"]}" to a later festival window or add a few months of runway '
            f"to free about Rs.{freed_default:,.0f}/mo toward this EMI."
        ),
        "rationale_lines": rationale_lines
        + [
            f"Proposed new EMI: Rs.{P:,.0f}/mo — shortfall vs safe/liquidity: Rs.{shortfall:,.0f}/mo.",
            "Festival dates use a fixed milestone calendar for planning; confirm with your own diary before applying.",
        ],
    }


def _build_affordability_check_payload(conn, user_id: int, P: float) -> dict[str, Any]:
    report = _build_emi_detection(conn, user_id)
    I = float(report.get("monthly_income") or 0)
    if I <= 0:
        I = 1.0
    E0 = float(report.get("total_emi_burden") or 0)
    safe_cap_rbi = float(report.get("max_new_emi_allowed") or 0)

    cur = conn.cursor()
    try:
        goals = _load_goals_for_affordability(cur, user_id)
    finally:
        cur.close()

    G_total = round(sum(g["monthly_target"] for g in goals), 2)
    B = _baseline_buffer(conn, user_id)
    liquidity_floor = max(0.0, I - E0 - G_total - B)

    affordable = (P <= safe_cap_rbi + _EPS) and (P <= liquidity_floor + _EPS)
    shortfall = max(0.0, P - safe_cap_rbi, P - liquidity_floor)

    inputs = {
        "income": round(I, 2),
        "existing_emi": round(E0, 2),
        "goals_monthly": G_total,
        "buffer": round(B, 2),
    }

    suggestion: Optional[dict[str, Any]] = None
    rationale_lines: list[str] = []

    rationale_lines.append(f"Income (basis for this check): Rs.{I:,.0f}/mo")
    rationale_lines.append(f"Existing EMI burden (detected): Rs.{E0:,.0f}/mo")
    rationale_lines.append(f"Active purchase goals pace: Rs.{G_total:,.0f}/mo total")
    rationale_lines.append(f"Living / liquidity buffer (policy): Rs.{B:,.0f}/mo")
    rationale_lines.append(f"RBI-style new-EMI headroom (30% line): Rs.{safe_cap_rbi:,.0f}/mo")
    rationale_lines.append(
        f"Cash left after EMIs + goals + buffer (before new EMI): Rs.{liquidity_floor:,.0f}/mo"
    )

    if not affordable and goals and shortfall > _EPS:
        defer_pool = [g for g in goals if (g.get("priority") or "MEDIUM").upper() != "HIGH"]
        defer_sorted = sorted(defer_pool, key=_defer_sort_key)
        milestones = _festivals_calendar_static()
        today = date.today()
        defer_entries: list[dict[str, Any]] = []
        for cand in defer_sorted:
            ent = _defer_entry_for_goal(conn, user_id, cand, shortfall, today, milestones, False)
            if ent:
                defer_entries.append(ent)

        if not defer_entries:
            high_pool = [g for g in goals if (g.get("priority") or "").upper() == "HIGH"]
            high_sorted = sorted(high_pool, key=_defer_sort_key)
            for cand in high_sorted:
                ent = _defer_entry_for_goal(conn, user_id, cand, shortfall, today, milestones, True)
                if ent:
                    defer_entries.append(ent)

        if defer_entries:
            default_gid = _default_goal_id_for_defer(defer_entries)
            if default_gid is None:
                default_gid = int(defer_entries[0]["goal_id"])
            suggestion = _compose_emi_suggestion_object(
                defer_entries, default_gid, shortfall, P, rationale_lines
            )
        else:
            suggestion = None
            if defer_pool:
                rationale_lines.append(
                    "No single MEDIUM/LOW goal had a festival milestone or generic deferral window we could model — "
                    "reduce the loan size, add income, or adjust multiple goals manually."
                )
            elif not defer_pool:
                rationale_lines.append(
                    "All active goals are HIGH priority — we do not auto-suggest changing them; adjust manually if needed."
                )

    if affordable:
        rationale_lines.append(
            f"Proposed Rs.{P:,.0f}/mo fits both RBI headroom (Rs.{safe_cap_rbi:,.0f}) and liquidity floor (Rs.{liquidity_floor:,.0f})."
        )

    return {
        "affordable": affordable,
        "proposed_new_emi": round(P, 2),
        "safe_cap_rbi": round(safe_cap_rbi, 2),
        "liquidity_floor": round(liquidity_floor, 2),
        "shortfall": round(shortfall, 2) if not affordable else 0.0,
        "inputs": inputs,
        "suggestion": suggestion,
        "rationale_lines": rationale_lines,
    }


class AffordabilityCheckBody(BaseModel):
    proposed_new_emi: float = Field(..., ge=0, le=5_000_000)


@router.post("/{user_id}/affordability-check")
def post_affordability_check(user_id: int, body: AffordabilityCheckBody, conn=Depends(get_db)):
    """
    Deterministic affordability: EMIs + goals + buffer vs income; optional defer plan.

    Manual test (replace UID and token if auth added later):
      curl -s -X POST http://127.0.0.1:8001/api/emi/1/affordability-check \\
        -H "Content-Type: application/json" \\
        -d "{\\"proposed_new_emi\\": 3000}" | jq .
    """
    if body.proposed_new_emi < 0:
        raise HTTPException(400, "proposed_new_emi must be non-negative")
    try:
        return _build_affordability_check_payload(conn, user_id, float(body.proposed_new_emi))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"affordability-check error: {exc}") from exc
