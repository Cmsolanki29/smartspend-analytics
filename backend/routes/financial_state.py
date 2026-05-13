"""
financial_state.py
══════════════════
Routes for the interconnected financial engine:
  GET  /api/financial-state/{user_id}          — full surplus breakdown
  GET  /api/notifications/{user_id}            — unread notifications
  POST /api/notifications/{user_id}/mark-read  — mark notifications as read
  GET  /api/impact-log/{user_id}               — last N impact log entries
  GET  /api/family-events/{user_id}            — list trips/events
  POST /api/family-events/{user_id}            — create event
  PATCH /api/family-events/{user_id}/{event_id}/postpone  — postpone + cascade
  PATCH /api/family-events/{user_id}/{event_id}/complete
  DELETE /api/family-events/{user_id}/{event_id}
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_db
from services.financial_engine import get_latest_snapshot, recalculate_financial_state

router = APIRouter(tags=["Financial State & Events"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class CreateEventBody(BaseModel):
    event_name: str = Field(..., min_length=2, max_length=200)
    event_type: str = Field(default="trip")
    planned_date: str = Field(..., min_length=8, max_length=12)
    estimated_cost: float = Field(..., ge=0, le=100_000_000)
    linked_purchase_goal_id: Optional[int] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class PostponeEventBody(BaseModel):
    new_date: str = Field(..., min_length=8, max_length=12)
    reason: str = Field(default="", max_length=500)
    cascade_linked_goal: bool = Field(default=True)


class MarkReadBody(BaseModel):
    notification_ids: list[int] = Field(default_factory=list)
    mark_all: bool = False


# ── Financial state ───────────────────────────────────────────────────────────

@router.get("/financial-state/{user_id}")
def get_financial_state(user_id: int, conn=Depends(get_db)):
    """Return the latest monthly snapshot with full breakdown. Always returns 200 — degrades gracefully."""
    cur = conn.cursor()
    cur.execute("SELECT id, COALESCE(monthly_income,0), COALESCE(monthly_fixed_expenses,0) FROM users WHERE id = %s", (user_id,))
    user_row = cur.fetchone()
    cur.close()
    if not user_row:
        raise HTTPException(404, "User not found")

    try:
        snap = get_latest_snapshot(conn, user_id)
        if snap:
            return snap
    except Exception:
        pass  # Fall through to minimal response

    # Minimal fallback — never return 500 for this non-critical endpoint
    income = float(user_row[1])
    return {
        "snapshot_id": None,
        "income": income,
        "fixed_expenses": float(user_row[2]),
        "emi_outgo": 0.0,
        "festival_reserve": 0.0,
        "event_reserve": 0.0,
        "purchase_reserve": 0.0,
        "surplus": income - float(user_row[2]),
        "surplus_status": "healthy",
        "purchase_detail": [],
        "festival_detail": [],
        "event_detail": [],
    }


@router.post("/financial-state/{user_id}/recalculate")
def force_recalculate(user_id: int, conn=Depends(get_db)):
    """Force a fresh recalculation (useful after bulk changes)."""
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")
    cur.close()
    try:
        snap = recalculate_financial_state(conn, user_id, "manual")
        return snap
    except Exception as exc:
        raise HTTPException(500, f"Recalculation failed: {exc}") from exc


# ── Notifications ─────────────────────────────────────────────────────────────

@router.get("/notifications/{user_id}")
def get_notifications(user_id: int, limit: int = 20, unread_only: bool = False, conn=Depends(get_db)):
    """Return notifications. Always returns 200."""
    try:
        cur = conn.cursor()
        if unread_only:
            cur.execute(
                "SELECT id, type, title, body, is_read, action_type, action_payload, created_at "
                "FROM notifications WHERE user_id=%s AND is_read=FALSE ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            )
        else:
            cur.execute(
                "SELECT id, type, title, body, is_read, action_type, action_payload, created_at "
                "FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            )
        rows = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id=%s AND is_read=FALSE", (user_id,))
        unread_count = int(cur.fetchone()[0])
        cur.close()
        return {
            "unread_count": unread_count,
            "notifications": [
                {
                    "id": r[0], "type": r[1], "title": r[2], "body": r[3],
                    "is_read": r[4], "action_type": r[5],
                    "action_payload": r[6] or {},
                    "created_at": r[7].isoformat() if r[7] else None,
                }
                for r in rows
            ],
        }
    except Exception:
        return {"unread_count": 0, "notifications": []}


@router.post("/notifications/{user_id}/mark-read")
def mark_notifications_read(user_id: int, body: MarkReadBody, conn=Depends(get_db)):
    cur = conn.cursor()
    if body.mark_all:
        cur.execute("UPDATE notifications SET is_read=TRUE WHERE user_id=%s", (user_id,))
    elif body.notification_ids:
        cur.execute(
            "UPDATE notifications SET is_read=TRUE WHERE user_id=%s AND id=ANY(%s)",
            (user_id, body.notification_ids),
        )
    conn.commit()
    cur.close()
    return {"ok": True}


# ── Impact log ────────────────────────────────────────────────────────────────

@router.get("/impact-log/{user_id}")
def get_impact_log(user_id: int, limit: int = 30, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, trigger_type, trigger_id, summary_text,
               surplus_before, surplus_after, affected_entities, created_at
        FROM impact_log
        WHERE user_id=%s ORDER BY created_at DESC LIMIT %s
        """,
        (user_id, limit),
    )
    rows = cur.fetchall()
    cur.close()
    return [
        {
            "id": r[0], "trigger_type": r[1], "trigger_id": r[2],
            "summary_text": r[3],
            "surplus_before": float(r[4]) if r[4] is not None else None,
            "surplus_after": float(r[5]) if r[5] is not None else None,
            "affected_entities": r[6] or [],
            "created_at": r[7].isoformat() if r[7] else None,
        }
        for r in rows
    ]


# ── Family Events / Trips ─────────────────────────────────────────────────────

def _serialize_event(r, cols):
    d = dict(zip(cols, r))
    for f in ("planned_date", "actual_date", "postponed_to_date"):
        if d.get(f):
            d[f] = str(d[f])
    for f in ("created_at", "updated_at"):
        if d.get(f):
            d[f] = d[f].isoformat()
    d["estimated_cost"] = float(d.get("estimated_cost") or 0)
    return d


@router.get("/family-events/{user_id}")
def list_family_events(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT fe.id, fe.user_id, fe.event_name, fe.event_type, fe.planned_date, fe.actual_date,
               fe.estimated_cost, fe.status, fe.postpone_reason, fe.postponed_to_date,
               fe.linked_purchase_goal_id, fe.notes, fe.created_at, fe.updated_at,
               pg.item_name AS linked_goal_name
        FROM family_events fe
        LEFT JOIN purchase_goals pg ON pg.id = fe.linked_purchase_goal_id
        WHERE fe.user_id = %s
        ORDER BY fe.planned_date ASC
        """,
        (user_id,),
    )
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    return [_serialize_event(r, cols) for r in rows]


@router.post("/family-events/{user_id}")
def create_family_event(user_id: int, body: CreateEventBody, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id=%s", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")

    try:
        planned_dt = datetime.strptime(body.planned_date[:10], "%Y-%m-%d").date()
    except ValueError:
        cur.close()
        raise HTTPException(400, "planned_date must be YYYY-MM-DD")

    cur.execute(
        """
        INSERT INTO family_events
            (user_id, event_name, event_type, planned_date, estimated_cost, linked_purchase_goal_id, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (user_id, body.event_name, body.event_type, planned_dt,
         body.estimated_cost, body.linked_purchase_goal_id, body.notes),
    )
    event_id = cur.fetchone()[0]
    conn.commit()

    # Recalculate
    snap = recalculate_financial_state(conn, user_id, "event_added", event_id,
                                       f"Family event '{body.event_name}' added.")
    cur.close()
    return {"event_id": event_id, "surplus_after": snap.get("surplus"), "surplus_status": snap.get("surplus_status")}


@router.patch("/family-events/{user_id}/{event_id}/postpone")
def postpone_family_event(user_id: int, event_id: int, body: PostponeEventBody, conn=Depends(get_db)):
    """Postpone a family event and optionally cascade to linked purchase goal."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, event_name, planned_date, linked_purchase_goal_id FROM family_events WHERE id=%s AND user_id=%s",
        (event_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        raise HTTPException(404, "Event not found")

    eid, ename, old_date, linked_goal_id = row

    try:
        new_dt = datetime.strptime(body.new_date[:10], "%Y-%m-%d").date()
    except ValueError:
        cur.close()
        raise HTTPException(400, "new_date must be YYYY-MM-DD")

    cur.execute(
        """
        UPDATE family_events
        SET status = 'postponed',
            postponed_to_date = %s,
            postpone_reason = %s,
            updated_at = NOW()
        WHERE id = %s
        """,
        (new_dt, body.reason or f"Postponed to {new_dt}", event_id),
    )

    cascaded_goal = None
    if body.cascade_linked_goal and linked_goal_id:
        cur.execute(
            """
            SELECT item_name, target_amount, saved_amount FROM purchase_goals
            WHERE id=%s AND user_id=%s AND UPPER(COALESCE(status,'ACTIVE')) NOT IN ('COMPLETED','CANCELLED')
            """,
            (linked_goal_id, user_id),
        )
        goal_row = cur.fetchone()
        if goal_row:
            gname, target, saved = goal_row
            remaining = max(0.0, float(target or 0) - float(saved or 0))
            from services.financial_engine import _months_between_dates
            from datetime import date as d
            months_left = max(1, _months_between_dates(d.today(), new_dt))
            new_monthly = round(remaining / months_left, 2)
            cur.execute(
                """
                UPDATE purchase_goals
                SET target_date = %s,
                    monthly_target = %s,
                    display_timeline_label = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (new_dt, new_monthly, f"Moved with {ename}", linked_goal_id),
            )
            cascaded_goal = {"goal_id": linked_goal_id, "goal_name": gname, "new_target_date": str(new_dt), "new_monthly_target": new_monthly}

    conn.commit()

    # Notifications
    notif_body = f"'{ename}' moved from {old_date} to {new_dt}."
    if cascaded_goal:
        notif_body += f" '{cascaded_goal['goal_name']}' purchase plan also updated to match. New pace: ₹{cascaded_goal['new_monthly_target']:,.0f}/mo."

    cur.execute(
        """
        INSERT INTO notifications (user_id, type, title, body, action_type, action_payload)
        VALUES (%s,'success',%s,%s,'navigate_to',%s)
        """,
        (user_id, f"'{ename}' moved to {new_dt.strftime('%b %Y')}",
         notif_body, json.dumps({"path": "/family-events"})),
    )
    conn.commit()

    snap = recalculate_financial_state(
        conn, user_id, "event_postponed", event_id,
        f"'{ename}' postponed to {new_dt}. Surplus recalculated."
    )

    cur.close()
    return {
        "ok": True,
        "event_id": event_id,
        "new_date": str(new_dt),
        "cascaded_goal": cascaded_goal,
        "surplus_after": snap.get("surplus"),
        "surplus_status": snap.get("surplus_status"),
        "notification": notif_body,
    }


@router.patch("/family-events/{user_id}/{event_id}/complete")
def complete_family_event(user_id: int, event_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute(
        "UPDATE family_events SET status='completed', actual_date=NOW()::date, updated_at=NOW() WHERE id=%s AND user_id=%s RETURNING event_name",
        (event_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        raise HTTPException(404, "Event not found")
    conn.commit()
    snap = recalculate_financial_state(conn, user_id, "event_completed", event_id, f"'{row[0]}' completed.")
    cur.close()
    return {"ok": True, "surplus_after": snap.get("surplus"), "surplus_status": snap.get("surplus_status")}


@router.delete("/family-events/{user_id}/{event_id}")
def delete_family_event(user_id: int, event_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute(
        "UPDATE family_events SET status='cancelled', updated_at=NOW() WHERE id=%s AND user_id=%s RETURNING event_name",
        (event_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        raise HTTPException(404, "Event not found")
    conn.commit()
    snap = recalculate_financial_state(conn, user_id, "event_cancelled", event_id, f"'{row[0]}' cancelled.")
    cur.close()
    return {"ok": True, "surplus_after": snap.get("surplus")}
