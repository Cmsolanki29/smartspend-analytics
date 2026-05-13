"""Proactive pattern alerts — upcoming charges, snooze, dismiss, savings, .ics export."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from db import get_db
from services.pattern_predictor import (
    expire_stale_alerts,
    predict_upcoming_charges,
    upsert_pattern_alerts,
)

router = APIRouter(prefix="/pattern-alerts", tags=["Pattern Alerts"])


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _build_ics(
    uid: str,
    summary: str,
    desc: str,
    start: datetime,
    end: datetime,
) -> str:
    fmt = "%Y%m%dT%H%M%SZ"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SmartSpend//Pattern Alert//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{datetime.utcnow().strftime(fmt)}",
        f"DTSTART:{start.strftime(fmt)}",
        f"DTEND:{end.strftime(fmt)}",
        f"SUMMARY:{_ics_escape(summary)}",
        f"DESCRIPTION:{_ics_escape(desc)}",
        "BEGIN:VALARM",
        "TRIGGER:-P1D",
        "ACTION:DISPLAY",
        "DESCRIPTION:Reminder 1 day before",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


class SnoozeBody(BaseModel):
    alert_id: int = Field(..., ge=1)
    snooze_hours: int = Field(24, ge=1, le=168)


class DismissBody(BaseModel):
    alert_id: int = Field(..., ge=1)
    reason: str = Field(..., min_length=2, max_length=80)


class ActionBody(BaseModel):
    alert_id: int = Field(..., ge=1)
    action: Literal["cancelled", "kept_service", "filed_dispute", "false_alarm"]
    notes: str | None = Field(None, max_length=500)


def _json_friendly_alert(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        elif isinstance(v, (list, tuple)) and k in (
            "cancellation_steps",
            "user_tips",
            "known_issues",
        ):
            out[k] = list(v) if v is not None else []
        elif hasattr(v, "__float__") and k in ("charge_amount", "predicted_confidence"):
            out[k] = float(v)
        else:
            out[k] = v
    return out


@router.get("/{user_id}/active")
def get_active_alerts(user_id: int, conn=Depends(get_db)):
    try:
        expire_stale_alerts(conn, user_id)
    except Exception:
        pass

    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
              a.id,
              a.pattern_type,
              a.merchant_name,
              a.charge_amount::float,
              a.charge_date,
              a.action_deadline,
              a.status,
              a.times_snoozed,
              a.predicted_confidence::float,
              a.created_at,
              (a.charge_date - CURRENT_DATE) AS days_until_charge,
              m.cancellation_method,
              m.cancellation_url,
              m.cancellation_phone,
              m.difficulty_rating,
              m.cancellation_steps,
              m.estimated_time_minutes,
              m.user_tips,
              m.known_issues
            FROM pattern_alerts a
            LEFT JOIN merchant_cancellation_info m
              ON LOWER(TRIM(m.merchant_name)) = LOWER(TRIM(a.merchant_name))
            WHERE a.user_id = %s
              AND a.status IN ('pending', 'snoozed')
              AND a.charge_date >= CURRENT_DATE
              AND (
                a.status = 'pending'
                OR (a.status = 'snoozed' AND (a.snooze_until IS NULL OR a.snooze_until <= NOW()))
              )
            ORDER BY a.charge_date ASC, a.charge_amount DESC;
            """,
            (user_id,),
        )
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        cur.close()

    critical, urgent, upcoming = [], [], []
    for r in rows:
        rj = _json_friendly_alert(r)
        d = int(r.get("days_until_charge") or 0)
        if d < 1:
            critical.append(rj)
        elif d <= 3:
            urgent.append(rj)
        else:
            upcoming.append(rj)

    return {
        "success": True,
        "alerts": {"critical": critical, "urgent": urgent, "upcoming": upcoming},
        "counts": {
            "total": len(critical) + len(urgent) + len(upcoming),
            "critical": len(critical),
            "urgent": len(urgent),
            "upcoming": len(upcoming),
        },
    }


@router.post("/{user_id}/generate")
def generate_alerts(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="User not found")
    finally:
        cur.close()

    predicted: list[dict[str, Any]] = []
    saved = 0
    try:
        expire_stale_alerts(conn, user_id)
        predicted = predict_upcoming_charges(conn, user_id)
        saved = upsert_pattern_alerts(conn, predicted)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "success": True,
        "predicted_count": len(predicted),
        "new_rows_inserted": saved,
        "message": f"Predicted {len(predicted)} charge window(s); {saved} new alert row(s).",
    }


@router.post("/{user_id}/snooze")
def snooze_alert(user_id: int, body: SnoozeBody, conn=Depends(get_db)):
    snooze_until = datetime.utcnow() + timedelta(hours=body.snooze_hours)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE pattern_alerts
            SET status = 'snoozed',
                times_snoozed = times_snoozed + 1,
                last_snoozed_at = NOW(),
                snooze_until = %s,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING id;
            """,
            (snooze_until, body.alert_id, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Alert not found")
        cur.execute(
            """
            INSERT INTO alert_action_log (alert_id, user_id, action_type, action_details)
            VALUES (%s, %s, 'snoozed', %s::jsonb);
            """,
            (body.alert_id, user_id, json.dumps({"snooze_hours": body.snooze_hours})),
        )
        cur.execute(
            """
            INSERT INTO notification_queue (alert_id, user_id, channel, scheduled_for, status)
            VALUES (%s, %s, 'in_app', %s, 'pending');
            """,
            (body.alert_id, user_id, snooze_until),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        cur.close()

    return {"success": True, "snooze_until": snooze_until.isoformat() + "Z"}


@router.post("/{user_id}/dismiss")
def dismiss_alert(user_id: int, body: DismissBody, conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE pattern_alerts
            SET status = 'dismissed',
                action_taken = %s,
                acted_at = NOW(),
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING id;
            """,
            (body.reason[:50], body.alert_id, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Alert not found")
        cur.execute(
            """
            INSERT INTO alert_action_log (alert_id, user_id, action_type, action_details)
            VALUES (%s, %s, 'dismissed', %s::jsonb);
            """,
            (body.alert_id, user_id, json.dumps({"reason": body.reason})),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        cur.close()

    return {"success": True}


@router.post("/{user_id}/action")
def record_action(user_id: int, body: ActionBody, conn=Depends(get_db)):
    cur = conn.cursor()
    savings_added = 0.0
    try:
        cur.execute(
            """
            SELECT charge_amount::float FROM pattern_alerts
            WHERE id = %s AND user_id = %s;
            """,
            (body.alert_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        amt = float(row[0] or 0)

        cur.execute(
            """
            UPDATE pattern_alerts
            SET status = 'acted',
                action_taken = %s,
                acted_at = NOW(),
                updated_at = NOW()
            WHERE id = %s AND user_id = %s;
            """,
            (body.action, body.alert_id, user_id),
        )
        cur.execute(
            """
            INSERT INTO alert_action_log (alert_id, user_id, action_type, action_details)
            VALUES (%s, %s, %s, %s::jsonb);
            """,
            (body.alert_id, user_id, body.action, json.dumps({"notes": body.notes or ""})),
        )

        if body.action == "cancelled":
            month_start = date.today().replace(day=1)
            cur.execute(
                """
                INSERT INTO user_savings_tracker (user_id, month, patterns_prevented, actual_savings)
                VALUES (%s, %s, 1, %s)
                ON CONFLICT (user_id, month) DO UPDATE SET
                  patterns_prevented = user_savings_tracker.patterns_prevented + 1,
                  actual_savings = user_savings_tracker.actual_savings + EXCLUDED.actual_savings;
                """,
                (user_id, month_start, amt),
            )
            savings_added = amt

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        cur.close()

    return {"success": True, "savings_added": savings_added}


@router.get("/{user_id}/savings")
def get_savings(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    month_start = date.today().replace(day=1)
    year_start = date.today().replace(month=1, day=1)

    try:
        cur.execute(
            """
            SELECT COALESCE(patterns_prevented,0), COALESCE(actual_savings,0)::float,
                   COALESCE(refunds_received,0)::float
            FROM user_savings_tracker WHERE user_id = %s AND month = %s;
            """,
            (user_id, month_start),
        )
        tm = cur.fetchone()
        this_month = {
            "patterns_prevented": int(tm[0] or 0) if tm else 0,
            "amount_saved": float(tm[1] or 0) if tm else 0.0,
            "refunds": float(tm[2] or 0) if tm else 0.0,
        }
        cur.execute(
            """
            SELECT COALESCE(SUM(patterns_prevented),0)::int,
                   COALESCE(SUM(actual_savings),0)::float,
                   COALESCE(SUM(refunds_received),0)::float
            FROM user_savings_tracker
            WHERE user_id = %s AND month >= %s;
            """,
            (user_id, year_start),
        )
        ty = cur.fetchone()
        this_year = {
            "patterns_prevented": int(ty[0] or 0),
            "amount_saved": float(ty[1] or 0),
            "refunds": float(ty[2] or 0),
        }
        cur.execute(
            """
            SELECT COALESCE(SUM(patterns_prevented),0)::int,
                   COALESCE(SUM(actual_savings),0)::float,
                   COALESCE(SUM(refunds_received),0)::float
            FROM user_savings_tracker WHERE user_id = %s;
            """,
            (user_id,),
        )
        at = cur.fetchone()
        all_time = {
            "patterns_prevented": int(at[0] or 0),
            "amount_saved": float(at[1] or 0),
            "refunds": float(at[2] or 0),
        }
    finally:
        cur.close()

    return {"success": True, "savings": {"this_month": this_month, "this_year": this_year, "all_time": all_time}}


@router.get("/{user_id}/calendar/{alert_id}")
def download_calendar(user_id: int, alert_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT a.merchant_name, a.charge_amount::float, a.charge_date, a.action_deadline,
                   m.cancellation_url
            FROM pattern_alerts a
            LEFT JOIN merchant_cancellation_info m
              ON LOWER(TRIM(m.merchant_name)) = LOWER(TRIM(a.merchant_name))
            WHERE a.id = %s AND a.user_id = %s;
            """,
            (alert_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        merchant, amt, cdate, adeadline, curl = row[0], float(row[1] or 0), row[2], row[3], row[4]
    finally:
        cur.close()

    if isinstance(adeadline, datetime):
        start = adeadline.replace(tzinfo=None)
    else:
        start = datetime.combine(cdate, datetime.min.time()) if isinstance(cdate, date) else datetime.utcnow()
    end = start + timedelta(hours=1)
    desc = (
        f"Possible charge ₹{amt:,.0f} on {cdate}. "
        f"Cancel: {curl or 'check merchant app / website'}."
    )
    ics = _build_ics(
        f"{alert_id}-{uuid.uuid4()}@smartspend.local",
        f"Review / cancel {merchant} before charge",
        desc,
        start,
        end,
    )
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="smartspend_alert_{alert_id}.ics"',
        },
    )
