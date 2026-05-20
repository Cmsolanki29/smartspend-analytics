"""User-defined date reminders for the Festival Planner (birthdays, fees, travel, etc.)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_db

router = APIRouter(prefix="/festivals", tags=["Festival important days"])

HORIZON_DAYS = 183


def _refresh_health_after_planner_change(conn, user_id: int, reason: str = "important_days_changed") -> None:
    try:
        from services.financial_engine import recalculate_financial_state

        recalculate_financial_state(conn, user_id, reason)
    except Exception:
        pass
DEFAULT_REMIND_OFFSETS = [30, 14, 7, 3, 1]


def _horizon_end(today: date) -> date:
    return date.fromordinal(today.toordinal() + HORIZON_DAYS)


def _next_yearly_occurrence_from(month: int, day: int, today: date) -> date:
    for y in range(today.year, today.year + 3):
        try:
            cand = date(y, month, day)
        except ValueError:
            cand = date(y, month, 28)
        if cand >= today:
            return cand
    return date(today.year + 2, month, min(day, 28))


def _effective_date(stored: date, repeats_yearly: bool, today: date) -> Optional[date]:
    if repeats_yearly:
        return _next_yearly_occurrence_from(stored.month, stored.day, today)
    return stored


def _in_timeline_window(eff: date, today: date, horizon: date) -> bool:
    return eff > today and eff <= horizon


def _offsets_for_days_until(days_until: Optional[int], custom: Optional[list[int]]) -> list[int]:
    base = sorted({int(x) for x in (custom or DEFAULT_REMIND_OFFSETS) if int(x) > 0}, reverse=True)
    if days_until is None or days_until <= 0:
        return base
    return [o for o in base if o < days_until] or ([1] if days_until >= 1 else [])


def _reminder_meta(
    eff: Optional[date],
    days_until: Optional[int],
    reminder_enabled: bool,
    offsets: list[int],
    today: date,
) -> dict[str, Any]:
    if not reminder_enabled or eff is None:
        return {
            "reminder_enabled": False,
            "remind_offsets": offsets,
            "next_reminder_on": None,
            "next_reminder_label": "Off",
            "days_until_reminder": None,
            "reminder_due": False,
            "reminder_status": "off",
        }

    applicable = _offsets_for_days_until(days_until, offsets)
    future: list[tuple[date, int]] = []
    for off in applicable:
        ping = eff - timedelta(days=off)
        if ping >= today:
            future.append((ping, off))
    future.sort(key=lambda x: x[0])

    if not future:
        return {
            "reminder_enabled": True,
            "remind_offsets": applicable,
            "next_reminder_on": None,
            "next_reminder_label": "This week",
            "days_until_reminder": 0 if days_until is not None and days_until <= 7 else None,
            "reminder_due": days_until is not None and days_until <= 3,
            "reminder_status": "due_soon" if days_until is not None and days_until <= 7 else "active",
        }

    next_ping, next_off = future[0]
    days_to_ping = (next_ping - today).days
    due = days_to_ping == 0
    status = "due_today" if due else ("due_soon" if days_to_ping <= 3 else "scheduled")
    return {
        "reminder_enabled": True,
        "remind_offsets": applicable,
        "next_reminder_on": next_ping.isoformat(),
        "next_reminder_label": f"T-{next_off}",
        "days_until_reminder": days_to_ping,
        "reminder_due": due,
        "reminder_status": status,
    }


def _select_rows(cur, user_id: int) -> list[tuple[Any, ...]]:
    try:
        cur.execute(
            """
            SELECT id, title, event_date, notes, repeats_yearly,
                   reminder_enabled, remind_offsets, estimated_budget
            FROM user_important_days
            WHERE user_id = %s
            ORDER BY event_date ASC, id ASC;
            """,
            (user_id,),
        )
        return cur.fetchall()
    except Exception:
        cur.connection.rollback()
        cur.execute(
            """
            SELECT id, title, event_date, notes, repeats_yearly
            FROM user_important_days
            WHERE user_id = %s
            ORDER BY event_date ASC, id ASC;
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        return [
            (r[0], r[1], r[2], r[3], r[4], True, DEFAULT_REMIND_OFFSETS, None)
            for r in rows
        ]


def _parse_offsets(raw: Any) -> list[int]:
    if raw is None:
        return list(DEFAULT_REMIND_OFFSETS)
    if isinstance(raw, (list, tuple)):
        return _offsets_for_days_until(9999, [int(x) for x in raw])
    return list(DEFAULT_REMIND_OFFSETS)


def _row_to_payload(row: tuple[Any, ...], today: date) -> dict[str, Any]:
    rid, title, stored, notes, repeats = row[0], row[1], row[2], row[3], row[4]
    reminder_enabled = bool(row[5]) if len(row) > 5 else True
    offsets = _parse_offsets(row[6] if len(row) > 6 else None)
    budget = float(row[7]) if len(row) > 7 and row[7] is not None else None

    horizon = _horizon_end(today)
    eff = _effective_date(stored, repeats, today)
    if eff is None:
        in_win = False
        days_until: Optional[int] = None
    else:
        in_win = _in_timeline_window(eff, today, horizon)
        days_until = (eff - today).days if eff >= today else None

    meta = _reminder_meta(eff, days_until, reminder_enabled, offsets, today)
    return {
        "id": int(rid),
        "title": title,
        "event_date": stored.isoformat(),
        "notes": notes or "",
        "repeats_yearly": bool(repeats),
        "effective_date": eff.isoformat() if eff else None,
        "days_until": days_until,
        "in_timeline_window": in_win,
        "estimated_budget": round(budget, 2) if budget is not None else None,
        **meta,
    }


def _insert_due_notification(conn, user_id: int, day: dict[str, Any], offset: int, today: date) -> None:
    eff_s = day.get("effective_date")
    if not eff_s:
        return
    eff = datetime.strptime(str(eff_s)[:10], "%Y-%m-%d").date()
    if eff - timedelta(days=offset) != today:
        return

    title = day["title"]
    budget = day.get("estimated_budget")
    budget_bit = f" Budget hint: ₹{budget:,.0f}." if budget else ""
    notif_title = f"📅 {title} — {offset} day reminder"
    body = (
        f"{title} is in {offset} day(s) ({eff.strftime('%d %b %Y')}). "
        f"Set aside spend or open your festival plan.{budget_bit}"
    )
    payload = json.dumps(
        {
            "important_day_id": day["id"],
            "offset_days": offset,
            "screen": "festivals",
            "effective_date": eff.isoformat(),
        }
    )

    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT 1 FROM notifications
            WHERE user_id = %s
              AND action_type = 'festival_date_reminder'
              AND (action_payload->>'important_day_id') = %s
              AND (action_payload->>'offset_days') = %s
              AND created_at::date = CURRENT_DATE
            LIMIT 1;
            """,
            (user_id, str(day["id"]), str(offset)),
        )
        if cur.fetchone():
            return
        cur.execute(
            """
            INSERT INTO notifications (user_id, type, title, body, action_type, action_payload)
            VALUES (%s, %s, %s, %s, 'festival_date_reminder', %s::jsonb);
            """,
            (
                user_id,
                "warning" if offset <= 3 else "info",
                notif_title,
                body,
                payload,
            ),
        )
    finally:
        cur.close()


def _sync_reminder_notifications(conn, user_id: int, days: list[dict[str, Any]]) -> None:
    today = date.today()
    for d in days:
        if not d.get("reminder_enabled"):
            continue
        offsets = d.get("remind_offsets") or DEFAULT_REMIND_OFFSETS
        for off in offsets:
            try:
                _insert_due_notification(conn, user_id, d, int(off), today)
            except Exception:
                conn.rollback()


class ImportantDayCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    event_date: date
    notes: str = Field(default="", max_length=4000)
    repeats_yearly: bool = False
    reminder_enabled: bool = True
    remind_offsets: list[int] = Field(default_factory=lambda: list(DEFAULT_REMIND_OFFSETS))
    estimated_budget: Optional[float] = Field(default=None, ge=0)


class ImportantDayUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    event_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    repeats_yearly: Optional[bool] = None
    reminder_enabled: Optional[bool] = None
    remind_offsets: Optional[list[int]] = None
    estimated_budget: Optional[float] = Field(default=None, ge=0)


class ReminderToggleBody(BaseModel):
    reminder_enabled: bool
    remind_offsets: Optional[list[int]] = None


@router.get("/{user_id}/important-days")
def list_important_days(user_id: int, conn=Depends(get_db)) -> dict[str, Any]:
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
        if not cur.fetchone():
            raise HTTPException(404, "User not found")
        rows = _select_rows(cur, user_id)
    finally:
        cur.close()

    today = date.today()
    days = [_row_to_payload(r, today) for r in rows]
    _sync_reminder_notifications(conn, user_id, days)
    return {"important_days": days}


@router.post("/{user_id}/important-days")
def create_important_day(user_id: int, body: ImportantDayCreate, conn=Depends(get_db)) -> dict[str, Any]:
    cur = conn.cursor()
    offsets = _offsets_for_days_until(9999, body.remind_offsets)
    try:
        cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
        if not cur.fetchone():
            raise HTTPException(404, "User not found")
        try:
            cur.execute(
                """
                INSERT INTO user_important_days (
                  user_id, title, event_date, notes, repeats_yearly,
                  reminder_enabled, remind_offsets, estimated_budget
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, title, event_date, notes, repeats_yearly,
                          reminder_enabled, remind_offsets, estimated_budget;
                """,
                (
                    user_id,
                    body.title.strip(),
                    body.event_date,
                    body.notes.strip() if body.notes else None,
                    body.repeats_yearly,
                    body.reminder_enabled,
                    offsets,
                    body.estimated_budget,
                ),
            )
        except Exception:
            conn.rollback()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO user_important_days (user_id, title, event_date, notes, repeats_yearly)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, title, event_date, notes, repeats_yearly;
                """,
                (
                    user_id,
                    body.title.strip(),
                    body.event_date,
                    body.notes.strip() if body.notes else None,
                    body.repeats_yearly,
                ),
            )
            row = cur.fetchone()
            row = (*row, body.reminder_enabled, offsets, body.estimated_budget)
        else:
            row = cur.fetchone()
    finally:
        cur.close()

    today = date.today()
    payload = _row_to_payload(row, today)
    _sync_reminder_notifications(conn, user_id, [payload])
    _refresh_health_after_planner_change(conn, user_id, "important_day_added")
    return {"important_day": payload}


@router.put("/{user_id}/important-days/{event_id}")
def update_important_day(
    user_id: int, event_id: int, body: ImportantDayUpdate, conn=Depends(get_db)
) -> dict[str, Any]:
    cur = conn.cursor()
    try:
        rows = _select_rows(cur, user_id)
        row = next((r for r in rows if int(r[0]) == event_id), None)
        if not row:
            raise HTTPException(404, "Important day not found")

        title = body.title.strip() if body.title is not None else row[1]
        evd = body.event_date if body.event_date is not None else row[2]
        notes = row[3]
        if body.notes is not None:
            notes = body.notes.strip() if body.notes else None
        repeats = body.repeats_yearly if body.repeats_yearly is not None else row[4]
        reminder_enabled = (
            body.reminder_enabled if body.reminder_enabled is not None else (bool(row[5]) if len(row) > 5 else True)
        )
        offsets = (
            _offsets_for_days_until(9999, body.remind_offsets)
            if body.remind_offsets is not None
            else _parse_offsets(row[6] if len(row) > 6 else None)
        )
        budget = body.estimated_budget if body.estimated_budget is not None else (row[7] if len(row) > 7 else None)

        try:
            cur.execute(
                """
                UPDATE user_important_days
                SET title = %s, event_date = %s, notes = %s, repeats_yearly = %s,
                    reminder_enabled = %s, remind_offsets = %s, estimated_budget = %s,
                    updated_at = NOW()
                WHERE id = %s AND user_id = %s
                RETURNING id, title, event_date, notes, repeats_yearly,
                          reminder_enabled, remind_offsets, estimated_budget;
                """,
                (title, evd, notes, repeats, reminder_enabled, offsets, budget, event_id, user_id),
            )
            out = cur.fetchone()
        except Exception:
            conn.rollback()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE user_important_days
                SET title = %s, event_date = %s, notes = %s, repeats_yearly = %s, updated_at = NOW()
                WHERE id = %s AND user_id = %s
                RETURNING id, title, event_date, notes, repeats_yearly;
                """,
                (title, evd, notes, repeats, event_id, user_id),
            )
            base = cur.fetchone()
            out = (*base, reminder_enabled, offsets, budget)
    finally:
        cur.close()

    today = date.today()
    payload = _row_to_payload(out, today)
    _sync_reminder_notifications(conn, user_id, [payload])
    _refresh_health_after_planner_change(conn, user_id, "important_day_updated")
    return {"important_day": payload}


@router.put("/{user_id}/important-days/{event_id}/reminder")
def toggle_important_day_reminder(
    user_id: int, event_id: int, body: ReminderToggleBody, conn=Depends(get_db)
) -> dict[str, Any]:
    return update_important_day(
        user_id,
        event_id,
        ImportantDayUpdate(
            reminder_enabled=body.reminder_enabled,
            remind_offsets=body.remind_offsets,
        ),
        conn,
    )


@router.delete("/{user_id}/important-days/{event_id}")
def delete_important_day(user_id: int, event_id: int, conn=Depends(get_db)) -> dict[str, Any]:
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM user_important_days WHERE id = %s AND user_id = %s RETURNING id;",
            (event_id, user_id),
        )
        deleted = cur.fetchone()
        if not deleted:
            raise HTTPException(404, "Important day not found")
    finally:
        cur.close()
    _refresh_health_after_planner_change(conn, user_id, "important_day_removed")
    return {"deleted": True, "id": event_id}
