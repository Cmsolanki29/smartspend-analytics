"""
financial_engine.py
═══════════════════
The core recalculation engine.  Every DB write that affects money must call
recalculate_financial_state(conn, user_id) immediately after.

Flow:
  1. Fetch income + fixed_expenses from users
  2. Sum active EMI burden from emi_records
  3. Sum purchase_goals monthly pace (active / saving)
  4. Sum festival_budgets monthly provision (upcoming within 90d)
  5. Sum family_events monthly reserve (upcoming within 180d)
  6. Compute available_surplus
  7. Upsert monthly_snapshots
  8. Write an impact_log row
  9. If surplus <= 0  → push RED ALERT notification
 10. If surplus < 2000 → push YELLOW WARNING notification
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

# ── Thresholds ────────────────────────────────────────────────────────────────
SURPLUS_CRITICAL = 0
SURPLUS_WARNING  = 2_000


def _push_notification(
    conn,
    user_id: int,
    ntype: str,
    title: str,
    body: str,
    action_type: str | None = None,
    action_payload: dict | None = None,
) -> None:
    """Insert a notification row (best-effort — never raises)."""
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO notifications (user_id, type, title, body, action_type, action_payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, ntype, title, body, action_type, json.dumps(action_payload or {})),
        )
        cur.close()
    except Exception:
        pass


def _months_between(d1: date, d2: date) -> float:
    """Positive fractional months from d1 to d2."""
    return max(0.0, (d2 - d1).days / 30.44)


def recalculate_financial_state(
    conn,
    user_id: int,
    trigger_type: str = "manual",
    trigger_id: int | None = None,
    trigger_summary: str | None = None,
) -> dict[str, Any]:
    """
    Full recalculation for user_id.  Returns the snapshot dict.
    Call this after every mutation that touches money.
    Safe to call even if some tables are missing — degrades gracefully.
    """
    cur = conn.cursor()
    today = date.today()
    month, year = today.month, today.year

    # ── 1. Income + fixed expenses ────────────────────────────────────────────
    cur.execute(
        "SELECT COALESCE(monthly_income,0), COALESCE(monthly_fixed_expenses,0) FROM users WHERE id=%s",
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        return {}
    monthly_income  = float(row[0])
    fixed_expenses  = float(row[1])

    # ── 2. EMI burden (manual emis + scanned emi_records) ────────────────────
    emis_sum = 0.0
    records_sum = 0.0
    try:
        cur.execute(
            """
            SELECT COALESCE(SUM(emi_amount), 0)::float FROM emis
            WHERE user_id = %s AND LOWER(COALESCE(status, 'active')) = 'active';
            """,
            (user_id,),
        )
        emis_sum = float((cur.fetchone() or [0])[0] or 0)
    except Exception:
        pass
    try:
        cur.execute(
            "SELECT COALESCE(SUM(detected_amount),0) FROM emi_records WHERE user_id=%s AND is_active=TRUE",
            (user_id,),
        )
        records_sum = float((cur.fetchone() or [0])[0] or 0)
    except Exception:
        pass
    if records_sum > 0 and emis_sum > 0:
        total_emi_outgo = emis_sum + records_sum
    elif records_sum > 0:
        total_emi_outgo = records_sum
    else:
        total_emi_outgo = emis_sum

    # ── 3. Purchase goals monthly reserve ────────────────────────────────────
    cur.execute(
        """
        SELECT id, item_name, COALESCE(monthly_target,0), target_date, priority
        FROM purchase_goals
        WHERE user_id=%s
          AND UPPER(COALESCE(status,'ACTIVE')) NOT IN ('COMPLETED','CANCELLED','PAUSED')
        """,
        (user_id,),
    )
    purchase_rows = cur.fetchall()
    purchase_monthly_reserve = sum(float(r[2]) for r in purchase_rows)
    purchase_detail = [
        {"id": r[0], "name": r[1], "monthly_target": float(r[2]),
         "target_date": str(r[3]) if r[3] else None, "priority": r[4]}
        for r in purchase_rows
    ]

    # ── 4. Festival monthly provision (upcoming within 180 days) ─────────────
    cur.execute(
        """
        SELECT id, festival_name, COALESCE(monthly_target,0), festival_date,
               COALESCE(planned_budget,0), COALESCE(saved_so_far,0)
        FROM festival_budgets
        WHERE user_id=%s
          AND festival_date >= CURRENT_DATE
          AND festival_date <= CURRENT_DATE + INTERVAL '180 days'
          AND UPPER(COALESCE(status,'UPCOMING')) <> 'COMPLETED'
        """,
        (user_id,),
    )
    festival_rows = cur.fetchall()
    festival_monthly_reserve = sum(float(r[2]) for r in festival_rows)
    festival_detail = [
        {"id": r[0], "name": r[1], "monthly_target": float(r[2]),
         "festival_date": str(r[3]) if r[3] else None,
         "planned_budget": float(r[4]), "saved_so_far": float(r[5])}
        for r in festival_rows
    ]

    # ── 5. Family events monthly reserve (upcoming within 180 days) ───────────
    cur.execute(
        """
        SELECT id, event_name, COALESCE(estimated_cost,0), planned_date, postponed_to_date, status
        FROM family_events
        WHERE user_id=%s
          AND UPPER(COALESCE(status,'planned')) NOT IN ('COMPLETED','CANCELLED')
        """,
        (user_id,),
    )
    event_rows = cur.fetchall()
    event_monthly_reserve = 0.0
    event_detail = []
    for erow in event_rows:
        eid, ename, cost, pdate, new_date, estatus = erow
        effective = new_date if new_date else pdate
        if not effective:
            continue
        months_left = _months_between(today, effective)
        if months_left <= 0 or months_left > 6:
            continue
        monthly_res = float(cost) / max(1.0, months_left)
        event_monthly_reserve += monthly_res
        event_detail.append({
            "id": eid, "name": ename, "estimated_cost": float(cost),
            "effective_date": str(effective), "status": estatus,
            "monthly_reserve": round(monthly_res, 2),
            "months_left": round(months_left, 1),
        })

    # ── 6. Surplus ────────────────────────────────────────────────────────────
    available_surplus = (
        monthly_income
        - fixed_expenses
        - total_emi_outgo
        - festival_monthly_reserve
        - event_monthly_reserve
        - purchase_monthly_reserve
    )

    surplus_status = (
        "critical" if available_surplus <= SURPLUS_CRITICAL
        else "warning" if available_surplus < SURPLUS_WARNING
        else "healthy"
    )

    breakdown = {
        "income": monthly_income,
        "fixed_expenses": fixed_expenses,
        "emi_outgo": total_emi_outgo,
        "festival_reserve": festival_monthly_reserve,
        "event_reserve": event_monthly_reserve,
        "purchase_reserve": purchase_monthly_reserve,
        "surplus": available_surplus,
        "surplus_status": surplus_status,
        "purchase_detail": purchase_detail,
        "festival_detail": festival_detail,
        "event_detail": event_detail,
    }

    # ── 7. Upsert monthly_snapshots ───────────────────────────────────────────
    snap_id = None
    try:
        cur.execute(
            """
            INSERT INTO monthly_snapshots
                (user_id, month, year, total_income, fixed_expenses, total_emi_outgo,
                 festival_monthly_reserve, event_monthly_reserve, purchase_monthly_reserve,
                 available_surplus, surplus_status, breakdown_json, computed_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT (user_id, month, year) DO UPDATE SET
                total_income              = EXCLUDED.total_income,
                fixed_expenses            = EXCLUDED.fixed_expenses,
                total_emi_outgo           = EXCLUDED.total_emi_outgo,
                festival_monthly_reserve  = EXCLUDED.festival_monthly_reserve,
                event_monthly_reserve     = EXCLUDED.event_monthly_reserve,
                purchase_monthly_reserve  = EXCLUDED.purchase_monthly_reserve,
                available_surplus         = EXCLUDED.available_surplus,
                surplus_status            = EXCLUDED.surplus_status,
                breakdown_json            = EXCLUDED.breakdown_json,
                computed_at               = NOW()
            RETURNING id
            """,
            (
                user_id, month, year,
                monthly_income, fixed_expenses, total_emi_outgo,
                festival_monthly_reserve, event_monthly_reserve, purchase_monthly_reserve,
                available_surplus, surplus_status, json.dumps(breakdown),
            ),
        )
        row2 = cur.fetchone()
        snap_id = row2[0] if row2 else None
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

    # ── 8. Impact log ─────────────────────────────────────────────────────────
    try:
        cur.execute(
            """
            INSERT INTO impact_log
                (user_id, trigger_type, trigger_id, summary_text, surplus_after, affected_entities)
            VALUES (%s,%s,%s,%s,%s,'[]'::jsonb)
            """,
            (
                user_id, trigger_type, trigger_id,
                trigger_summary or f"Recalculated. Surplus: \u20b9{available_surplus:,.0f}/mo ({surplus_status}).",
                available_surplus,
            ),
        )
    except Exception:
        pass

    # ── 9. Notifications (only for meaningful user-triggered events) ──────────
    silent = trigger_type in ("manual", "startup", "purchase_goal_added")
    if not silent:
        if available_surplus <= SURPLUS_CRITICAL:
            _push_notification(
                conn, user_id, "alert",
                "Budget is in the red!",
                f"Monthly budget is \u20b9{abs(available_surplus):,.0f} short after all commitments. "
                "Open Dashboard to see what's eating your surplus.",
                "navigate_to", {"path": "/dashboard"},
            )
        elif available_surplus < SURPLUS_WARNING:
            _push_notification(
                conn, user_id, "warning",
                "Surplus is very tight",
                f"Only \u20b9{available_surplus:,.0f}/mo left after all commitments. "
                "Consider pausing a purchase plan or reducing festival reserve.",
                "navigate_to", {"path": "/dashboard"},
            )

    cur.close()
    try:
        conn.commit()
    except Exception:
        pass

    health_payload: dict[str, Any] = {}
    try:
        from services.scorer import refresh_user_health_score

        hs = refresh_user_health_score(conn, user_id, month, year)
        health_payload = {
            "health_score": hs.score,
            "health_grade": hs.grade,
            "health_trend": hs.trend,
        }
    except Exception:
        pass

    return {"snapshot_id": snap_id, **breakdown, **health_payload}


def get_latest_snapshot(conn, user_id: int) -> dict[str, Any]:
    """
    Return the latest monthly snapshot for a user.
    Recomputes if no snapshot exists for the current month.
    Uses cached snapshot if computed within the last 30 minutes.
    """
    cur = conn.cursor()
    today = date.today()
    cur.execute(
        """
        SELECT id, total_income, fixed_expenses, total_emi_outgo,
               festival_monthly_reserve, event_monthly_reserve, purchase_monthly_reserve,
               available_surplus, surplus_status, breakdown_json, computed_at
        FROM monthly_snapshots
        WHERE user_id=%s AND month=%s AND year=%s
        ORDER BY computed_at DESC LIMIT 1
        """,
        (user_id, today.month, today.year),
    )
    row = cur.fetchone()
    cur.close()

    if not row:
        return recalculate_financial_state(conn, user_id, "startup")

    # Check staleness (>30 minutes → recompute)
    computed_at = row[10]
    try:
        if computed_at.tzinfo is not None:
            age_seconds = (datetime.now(timezone.utc) - computed_at).total_seconds()
        else:
            age_seconds = (datetime.utcnow() - computed_at).total_seconds()
    except Exception:
        age_seconds = 0

    if age_seconds > 1800:  # 30 minutes
        return recalculate_financial_state(conn, user_id, "startup")

    # Return cached
    snap = row[9] or {}
    return {
        "snapshot_id": row[0],
        "income": float(row[1] or 0),
        "fixed_expenses": float(row[2] or 0),
        "emi_outgo": float(row[3] or 0),
        "festival_reserve": float(row[4] or 0),
        "event_reserve": float(row[5] or 0),
        "purchase_reserve": float(row[6] or 0),
        "surplus": float(row[7] or 0),
        "surplus_status": row[8] or "healthy",
        **snap,
    }
