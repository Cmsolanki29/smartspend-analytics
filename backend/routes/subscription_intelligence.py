"""
Subscription Intelligence API — device usage, verdicts, substitutions, reminders.
SIMULATED: real impl uses Android UsageStatsManager via companion mobile SDK (device_links + app_usage_signals are seeded).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from db import get_db
from routes.subscription_graveyard import build_subscription_dashboard
from utils.auth import get_current_user_id
from services.subscription_intelligence.schema_bootstrap import ensure_subscription_intelligence_schema
from services.subscription_intelligence import (
    apply_reminder_action,
    detect_substitutions,
    evaluate_subscription,
    fetch_recommendation_paragraph,
    persist_verdict,
    schedule_reminders_for_subscription,
    simulate_next_day,
)
from services.subscription_intelligence.substitution_detector import (
    detect_category_migrations,
    save_category_migration_insights,
)
from services.subscription_intelligence.verdict_engine import generate_all_verdict_reports
from services.subscription_intelligence.connected_apps_sync import (
    log_subscription_event,
    sync_connected_apps_for_user,
)
from services.subscription_intelligence.insight_feed import (
    fetch_intelligence_insights,
    mark_insight_read,
    persist_substitution_insights,
    sync_verdict_insights,
)
from services.subscription_intelligence.reminder_scheduler import (
    create_reminders_with_escalation,
    fetch_pending_reminders,
    fetch_reminders_feed,
)

router = APIRouter(prefix="/subscription-intelligence", tags=["Subscription Intelligence"])


def _require_self(user_id: int, auth_user_id: int) -> None:
    if int(user_id) != int(auth_user_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You may only access subscription intelligence for your own account.",
        )


def subscription_intel_connection(conn=Depends(get_db)):
    """Ensure migration 021 DDL exists before any subscription-intelligence query."""
    ensure_subscription_intelligence_schema(conn)
    return conn


class DeviceLinkBody(BaseModel):
    # SIMULATED: production version uses Android UsageStatsManager via companion mobile SDK
    device_type: str = Field(default="simulated", description="android | ios | simulated")
    permissions: dict[str, bool] = Field(default_factory=dict)
    apps_linked: list[str] = Field(default_factory=list)


class ReminderActionBody(BaseModel):
    action: str = Field(..., description="cancel_now | remind_later | keep")
    accountability_reason: str | None = Field(
        default=None,
        max_length=4000,
        description="Required for remind_later only when subscription reminder_escalation_tier >= 2 (min 10 chars).",
    )


def _device_row(conn, user_id: int) -> dict[str, Any] | None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, linked_at, device_type, permissions, apps_linked, link_status
            FROM device_links WHERE user_id = %s AND link_status = 'active' LIMIT 1;
            """,
            (user_id,),
        )
        r = cur.fetchone()
        if not r:
            return None
        perms = r[3]
        apps = r[4]
        if isinstance(perms, str):
            perms = json.loads(perms)
        if isinstance(apps, str):
            apps = json.loads(apps)
        return {
            "id": r[0],
            "linked_at": r[1].isoformat() if r[1] else None,
            "device_type": r[2],
            "permissions": perms,
            "apps_linked": apps or [],
            "link_status": r[5],
        }
    finally:
        cur.close()


def _intel_rows(conn, user_id: int) -> dict[int, dict[str, Any]]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, merchant, monthly_cost, intelligence_category, linked_app_package,
                   current_verdict, verdict_confidence, verdict_reason, verdict_monthly_waste,
                   next_billing_date, billing_day, sub_lifecycle, is_pro, last_evaluated_at,
                   COALESCE(reminder_escalation_tier, 1)
            FROM subscriptions WHERE user_id = %s ORDER BY merchant;
            """,
            (user_id,),
        )
        out: dict[int, dict[str, Any]] = {}
        for row in cur.fetchall():
            sid = int(row[0])
            out[sid] = {
                "id": sid,
                "merchant": row[1],
                "monthly_cost_intel": float(row[2] or 0),
                "intelligence_category": row[3],
                "linked_app_package": row[4],
                "current_verdict": row[5],
                "verdict_confidence": row[6],
                "verdict_reason": row[7],
                "verdict_monthly_waste": float(row[8] or 0),
                "next_billing_date": row[9].isoformat() if row[9] else None,
                "billing_day": row[10],
                "sub_lifecycle": row[11],
                "is_pro": bool(row[12]) if row[12] is not None else False,
                "last_evaluated_at": row[13].isoformat() if row[13] else None,
                "reminder_escalation_tier": int(row[14] or 1),
            }
        return out
    finally:
        cur.close()


def _merge_by_merchant(subs_list: list[dict], by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    by_merchant = {v["merchant"]: v for v in by_id.values()}
    merged = []
    for s in subs_list:
        m = s.get("merchant")
        row = by_merchant.get(m)
        base = {**s}
        if row:
            base.update(
                {
                    "subscription_id": row["id"],
                    "intelligence_category": row.get("intelligence_category"),
                    "linked_app_package": row.get("linked_app_package"),
                    "current_verdict": row.get("current_verdict"),
                    "verdict_confidence": row.get("verdict_confidence"),
                    "verdict_reason": row.get("verdict_reason"),
                    "verdict_monthly_waste": row.get("verdict_monthly_waste"),
                    "next_billing_date": row.get("next_billing_date"),
                    "billing_day": row.get("billing_day"),
                    "sub_lifecycle": row.get("sub_lifecycle"),
                    "is_pro": row.get("is_pro"),
                    "last_evaluated_at": row.get("last_evaluated_at"),
                    "reminder_escalation_tier": row.get("reminder_escalation_tier"),
                }
            )
        merged.append(base)
    return merged


def _usage_rollups(conn, user_id: int, since: date) -> dict[str, list[dict[str, Any]]]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT app_package, signal_date, usage_minutes
            FROM app_usage_signals
            WHERE user_id = %s AND signal_date >= %s
            ORDER BY app_package, signal_date;
            """,
            (user_id, since),
        )
        by_pkg: dict[str, list[dict[str, Any]]] = {}
        for pkg, sd, um in cur.fetchall():
            by_pkg.setdefault(str(pkg), []).append({"d": sd.isoformat(), "m": int(um or 0)})
        return by_pkg
    finally:
        cur.close()


def _waste_ledger_yearly(conn, user_id: int) -> float:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COALESCE(SUM(verdict_monthly_waste), 0)::float
            FROM subscriptions WHERE user_id = %s;
            """,
            (user_id,),
        )
        return float(cur.fetchone()[0] or 0) * 12.0
    finally:
        cur.close()


@router.get("/health")
def subscription_intelligence_health() -> dict[str, Any]:
    """Liveness for subscription-intelligence stack (no auth)."""
    return {"ok": True, "service": "subscription-intelligence", "phase": "3"}


@router.get("/{user_id}/ai-summary")
def get_ai_summary(
    user_id: int,
    conn=Depends(subscription_intel_connection),
    auth_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    """
    Phase 3 bundle: batch verdict buckets, category migrations, and quick financial rollups.
    Requires Bearer token; user_id must match JWT.
    """
    _require_self(user_id, auth_user_id)
    verdicts = generate_all_verdict_reports(conn, user_id)
    migrations = detect_category_migrations(conn, user_id)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COUNT(*)::int, COALESCE(SUM(verdict_monthly_waste), 0)::float
            FROM subscriptions
            WHERE user_id = %s;
            """,
            (user_id,),
        )
        total_subs, waste_sum = cur.fetchone()
    finally:
        cur.close()
    saved_ytd = 0.0
    cancelled_ytd = 0
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COALESCE(SUM(amount_saved), 0)::float,
                   COALESCE(SUM(subscriptions_cancelled), 0)::int
            FROM user_subscription_savings
            WHERE user_id = %s AND month >= date_trunc('year', CURRENT_DATE)::date;
            """,
            (user_id,),
        )
        saved_row = cur.fetchone()
        saved_ytd = float(saved_row[0] or 0)
        cancelled_ytd = int(saved_row[1] or 0)
    except Exception:
        saved_ytd = 0.0
        cancelled_ytd = 0
    finally:
        try:
            cur.close()
        except Exception:
            pass
    at_risk = len(verdicts.get("declining") or []) + len(verdicts.get("dormant") or [])
    return {
        "success": True,
        "verdicts": verdicts,
        "migrations": migrations,
        "summary": {
            "subscriptions_tracked": int(total_subs or 0),
            "thriving_count": len(verdicts.get("thriving") or []),
            "declining_count": len(verdicts.get("declining") or []),
            "dormant_count": len(verdicts.get("dormant") or []),
            "upgrade_recommended_count": len(verdicts.get("upgrade_recommended") or []),
            "at_risk_count": at_risk,
            "verdict_monthly_waste_sum_inr": round(float(waste_sum or 0), 2),
            "verdict_yearly_waste_sum_inr": round(float(waste_sum or 0) * 12.0, 2),
            "migrations_detected": len(migrations),
            "savings_amount_saved_ytd_inr": round(saved_ytd, 2),
            "subscriptions_cancelled_ytd": cancelled_ytd,
        },
    }


@router.get("/{user_id}/verdicts/snapshot")
def get_verdicts_snapshot(
    user_id: int,
    conn=Depends(subscription_intel_connection),
    auth_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    _require_self(user_id, auth_user_id)
    verdicts = generate_all_verdict_reports(conn, user_id)
    return {
        "success": True,
        "verdicts": verdicts,
        "counts": {
            "thriving": len(verdicts.get("thriving") or []),
            "declining": len(verdicts.get("declining") or []),
            "dormant": len(verdicts.get("dormant") or []),
            "upgrade_recommended": len(verdicts.get("upgrade_recommended") or []),
        },
    }


@router.get("/{user_id}/migrations/category")
def get_category_migrations(
    user_id: int,
    conn=Depends(subscription_intel_connection),
    auth_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    _require_self(user_id, auth_user_id)
    rows = detect_category_migrations(conn, user_id)
    return {"success": True, "migrations": rows, "count": len(rows)}


@router.post("/{user_id}/migrations/category/persist")
def post_persist_category_migrations(
    user_id: int,
    conn=Depends(subscription_intel_connection),
    auth_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Run category migration detector and upsert rows into subscription_intelligence_insights."""
    _require_self(user_id, auth_user_id)
    rows = detect_category_migrations(conn, user_id)
    n = save_category_migration_insights(conn, user_id, rows) if rows else 0
    return {"success": True, "detected": len(rows), "upserted": n}


@router.post("/{user_id}/reminders/schedule-upcoming")
def post_schedule_upcoming_reminders(
    user_id: int,
    conn=Depends(subscription_intel_connection),
    auth_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Create / refresh scheduled_reminders for renewals in the next 30 days (tier-aware)."""
    _require_self(user_id, auth_user_id)
    summary = create_reminders_with_escalation(conn, user_id)
    return {"success": True, **summary}


@router.get("/{user_id}/insights/feed")
def get_insights_feed(
    user_id: int,
    conn=Depends(subscription_intel_connection),
    auth_user_id: int = Depends(get_current_user_id),
    unread_only: bool = Query(False),
    limit: int = Query(40, ge=1, le=100),
) -> dict[str, Any]:
    """List subscription_intelligence_insights (read_at null = unread)."""
    _require_self(user_id, auth_user_id)
    rows = fetch_intelligence_insights(conn, user_id, limit=limit)
    if unread_only:
        rows = [r for r in rows if not r.get("read_at")]
    return {"success": True, "insights": rows, "count": len(rows)}


@router.get("/{user_id}/savings")
def get_subscription_savings(
    user_id: int,
    conn=Depends(subscription_intel_connection),
    auth_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    _require_self(user_id, auth_user_id)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COALESCE(subscriptions_cancelled, 0), COALESCE(amount_saved, 0),
                   COALESCE(waste_prevented_monthly, 0), COALESCE(waste_prevented_yearly, 0)
            FROM user_subscription_savings
            WHERE user_id = %s AND month = date_trunc('month', CURRENT_DATE)::date;
            """,
            (user_id,),
        )
        this_month = cur.fetchone() or (0, 0, 0, 0)
        cur.execute(
            """
            SELECT COALESCE(SUM(subscriptions_cancelled), 0), COALESCE(SUM(amount_saved), 0),
                   COALESCE(SUM(waste_prevented_yearly), 0)
            FROM user_subscription_savings
            WHERE user_id = %s AND month >= date_trunc('year', CURRENT_DATE)::date;
            """,
            (user_id,),
        )
        ytd = cur.fetchone() or (0, 0, 0)
        cur.execute(
            """
            SELECT COALESCE(SUM(subscriptions_cancelled), 0), COALESCE(SUM(amount_saved), 0)
            FROM user_subscription_savings
            WHERE user_id = %s;
            """,
            (user_id,),
        )
        all_time = cur.fetchone() or (0, 0)
    except Exception:
        this_month = (0, 0, 0, 0)
        ytd = (0, 0, 0)
        all_time = (0, 0)
    finally:
        cur.close()
    return {
        "success": True,
        "this_month": {
            "subscriptions_cancelled": int(this_month[0] or 0),
            "amount_saved_inr": float(this_month[1] or 0),
            "waste_prevented_monthly_inr": float(this_month[2] or 0),
            "waste_prevented_yearly_inr": float(this_month[3] or 0),
        },
        "this_year": {
            "subscriptions_cancelled": int(ytd[0] or 0),
            "amount_saved_inr": float(ytd[1] or 0),
            "waste_prevented_yearly_inr": float(ytd[2] or 0),
        },
        "all_time": {
            "subscriptions_cancelled": int(all_time[0] or 0),
            "amount_saved_inr": float(all_time[1] or 0),
        },
    }


@router.get("/{user_id}/hub")
def intelligence_hub(user_id: int, conn=Depends(subscription_intel_connection)):
    base = build_subscription_dashboard(user_id, conn)
    by_id = _intel_rows(conn, user_id)
    device = _device_row(conn, user_id)
    merged = _merge_by_merchant(base.get("subscriptions") or [], by_id)
    seen_m = {s["merchant"] for s in merged}
    for row in by_id.values():
        if row["merchant"] not in seen_m:
            merged.append(
                {
                    "merchant": row["merchant"],
                    "amount": row["monthly_cost_intel"],
                    "billing_cycle": "MONTHLY",
                    "category": row.get("intelligence_category") or "other",
                    "status": "SUSPICIOUS",
                    "usage_score": 50,
                    "last_used_days": 14,
                    "monthly_cost": row["monthly_cost_intel"],
                    "times_charged": 3,
                    "first_charged": (date.today() - timedelta(days=120)).isoformat(),
                    "last_charged": (date.today() - timedelta(days=3)).isoformat(),
                    "insight": "Device-intelligence row (bank scan may not yet cluster this merchant).",
                    "subscription_id": row["id"],
                    "intelligence_category": row.get("intelligence_category"),
                    "linked_app_package": row.get("linked_app_package"),
                    "current_verdict": row.get("current_verdict"),
                    "verdict_confidence": row.get("verdict_confidence"),
                    "verdict_reason": row.get("verdict_reason"),
                    "verdict_monthly_waste": row.get("verdict_monthly_waste"),
                    "next_billing_date": row.get("next_billing_date"),
                    "billing_day": row.get("billing_day"),
                    "sub_lifecycle": row.get("sub_lifecycle"),
                    "is_pro": row.get("is_pro"),
                    "last_evaluated_at": row.get("last_evaluated_at"),
                    "reminder_escalation_tier": row.get("reminder_escalation_tier"),
                }
            )
            seen_m.add(row["merchant"])
    roll = _usage_rollups(conn, user_id, date.today() - timedelta(days=89))
    for s in merged:
        pkg = s.get("linked_app_package")
        if pkg and pkg in roll:
            s["usage_series"] = roll[pkg][-45:]
    subs = fetch_pending_reminders(conn, user_id)
    substitutions: list[dict[str, Any]] = []
    try:
        substitutions = detect_substitutions(conn, user_id)
    except Exception:
        substitutions = []
    try:
        persist_substitution_insights(conn, user_id, substitutions)
    except Exception:
        pass
    try:
        sync_verdict_insights(conn, user_id)
    except Exception:
        pass

    connected_apps: list[dict[str, Any]] = []
    if device is not None:
        try:
            connected_apps = sync_connected_apps_for_user(conn, user_id)
        except Exception:
            connected_apps = []

    try:
        intelligence_insights = fetch_intelligence_insights(conn, user_id, limit=20)
    except Exception:
        intelligence_insights = []

    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT EXISTS(
              SELECT 1 FROM subscriptions
              WHERE user_id = %s AND COALESCE(reminder_escalation_tier, 1) >= 2
            );
            """,
            (user_id,),
        )
        escalation_active = bool(cur.fetchone()[0])
    finally:
        cur.close()

    yearly = round(_waste_ledger_yearly(conn, user_id), 2)
    monthly_intel = round(sum(float(r.get("verdict_monthly_waste") or 0) for r in by_id.values()), 2)
    discovery_total = round(sum(float(s.get("monthly_cost") or 0) for s in merged), 2)

    legacy_ai = str(base.get("ai_advice") or "").strip()
    monthly_legacy = float(base.get("monthly_waste") or 0)
    _legacy_zero_waste_copy = (
        monthly_legacy < 0.005
        and monthly_intel > 0.005
        and (
            not legacy_ai
            or "Rs.0" in legacy_ai
            or "₹0" in legacy_ai
            or "0/month" in legacy_ai
            or "Consider cancelling unused subscriptions" in legacy_ai
        )
    )
    if _legacy_zero_waste_copy:
        legacy_ai = (
            f"Verdict-classified waste is about ₹{monthly_intel:,.0f}/month "
            f"(₹{monthly_intel * 12:,.0f}/year) across underused subscriptions. "
            f"Review declining and dormant cards first, then decide on upgrades."
        )
    elif monthly_intel > monthly_legacy + 0.5 and monthly_intel > 0.005:
        legacy_ai = (
            f"Verdict-classified waste is about ₹{monthly_intel:,.0f}/month "
            f"(₹{monthly_intel * 12:,.0f}/year). {legacy_ai}"
        ).strip()

    return {
        "discovery": {
            "count": len(merged),
            "monthly_total_inr": discovery_total,
            "message": f"We found {len(merged)} subscriptions across your account — ₹{discovery_total:,.0f}/month.",
        },
        "device_linked": device is not None,
        "device": device,
        "connected_apps": connected_apps,
        "intelligence_insights": intelligence_insights,
        "reminder_escalation_active": escalation_active,
        "subscriptions": merged,
        "substitutions": substitutions,
        "pending_reminders": subs,
        "waste_ledger_yearly_saved_inr": yearly,
        "verdict_monthly_waste_sum_inr": monthly_intel,
        "legacy": {"ai_advice": legacy_ai or base.get("ai_advice"), "cancel_guide": base.get("cancel_guide")},
    }


@router.post("/{user_id}/device-link")
def post_device_link(
    user_id: int,
    body: DeviceLinkBody,
    conn=Depends(subscription_intel_connection),
    auth_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Upsert device link, seed usage + subscriptions for **this JWT user only** (path id must match)."""
    _require_self(user_id, auth_user_id)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO device_links (user_id, device_type, permissions, apps_linked, link_status)
            VALUES (%s, %s, %s::jsonb, %s::jsonb, 'active')
            ON CONFLICT (user_id) DO UPDATE SET
              linked_at = NOW(),
              device_type = EXCLUDED.device_type,
              permissions = EXCLUDED.permissions,
              apps_linked = EXCLUDED.apps_linked,
              link_status = 'active';
            """,
            (
                user_id,
                body.device_type,
                json.dumps(body.permissions or {}),
                json.dumps(body.apps_linked or []),
            ),
        )
    finally:
        cur.close()
    from services.subscription_intelligence.seed_demo import run_seed_for_user

    run_seed_for_user(conn, user_id, wipe_device=False)
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM subscriptions WHERE user_id=%s ORDER BY id;", (user_id,))
        sids = [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
    for sid in sids:
        vr = evaluate_subscription(conn, sid)
        if vr is not None:
            persist_verdict(conn, sid, vr)
            schedule_reminders_for_subscription(conn, sid)
    try:
        sync_connected_apps_for_user(conn, user_id)
        log_subscription_event(
            conn,
            user_id,
            "device_intelligence_linked",
            payload={"device_type": body.device_type, "app_count": len(body.apps_linked or [])},
        )
    except Exception:
        pass
    return {"ok": True, "device": _device_row(conn, user_id), "evaluated_subscriptions": len(sids)}


@router.post("/{user_id}/subscriptions/{subscription_id}/evaluate")
def post_evaluate(user_id: int, subscription_id: int, conn=Depends(subscription_intel_connection)):
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id FROM subscriptions WHERE id = %s;", (subscription_id,))
        r = cur.fetchone()
        if not r or int(r[0]) != user_id:
            raise HTTPException(status_code=404, detail="Subscription not found")
    finally:
        cur.close()
    vr = evaluate_subscription(conn, subscription_id)
    if not vr:
        raise HTTPException(status_code=400, detail="Could not evaluate")
    persist_verdict(conn, subscription_id, vr)
    schedule_reminders_for_subscription(conn, subscription_id)
    return {
        "verdict": vr.verdict,
        "confidence": vr.confidence,
        "reason": vr.reason,
        "monthly_waste": vr.monthly_waste,
        "substitution": vr.substitution,
    }


@router.get("/{user_id}/subscriptions/{subscription_id}/recommendation")
def get_recommendation(user_id: int, subscription_id: int, conn=Depends(subscription_intel_connection)):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT merchant, monthly_cost, intelligence_category, current_verdict, verdict_reason, linked_app_package
            FROM subscriptions WHERE id = %s AND user_id = %s;
            """,
            (subscription_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        merchant, monthly_cost, cat, verdict, reason, pkg = row
    finally:
        cur.close()
    today = date.today()
    d0 = today - timedelta(days=30)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COALESCE(SUM(usage_minutes), 0)::bigint
            FROM app_usage_signals WHERE user_id = %s AND app_package = %s AND signal_date >= %s;
            """,
            (user_id, pkg or "", d0),
        )
        mins = int(cur.fetchone()[0] or 0)
    finally:
        cur.close()
    usage_summary = f"Last 30d in-app time ≈ {mins} minutes ({mins/60:.1f} hours)."
    sub_name = str(merchant)
    substitute_name = None
    if verdict == "dead" and pkg:
        try:
            subs = detect_substitutions(conn, user_id)
            for s in subs:
                if int(s.get("subscription_id") or 0) == subscription_id:
                    substitute_name = s.get("to_package")
                    break
        except Exception:
            substitute_name = None
    paragraph = fetch_recommendation_paragraph(
        name=sub_name,
        monthly_cost=float(monthly_cost or 0),
        category=str(cat or "other"),
        verdict=str(verdict or "declining"),
        reason=str(reason or ""),
        usage_summary=usage_summary,
        substitute_name=substitute_name,
    )
    return {"paragraph": paragraph}


@router.get("/{user_id}/substitutions")
def get_substitutions(user_id: int, conn=Depends(subscription_intel_connection)):
    return {"insights": detect_substitutions(conn, user_id)}


@router.get("/{user_id}/reminders/pending")
def get_reminders(
    user_id: int,
    include_upcoming: bool = Query(
        False,
        description="If true, return pending/shown/snoozed reminders (T-10, T-3, …), not only due/shown.",
    ),
    conn=Depends(subscription_intel_connection),
    auth_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    _require_self(user_id, auth_user_id)
    if include_upcoming:
        return {"reminders": fetch_reminders_feed(conn, user_id)}
    return {"reminders": fetch_pending_reminders(conn, user_id)}


@router.post("/{user_id}/reminders/{reminder_id}/action")
def post_reminder_action(
    user_id: int,
    reminder_id: int,
    body: ReminderActionBody,
    conn=Depends(subscription_intel_connection),
    auth_user_id: int = Depends(get_current_user_id),
):
    _require_self(user_id, auth_user_id)
    res = apply_reminder_action(
        conn,
        reminder_id,
        user_id,
        body.action,
        body.accountability_reason,
    )
    if not res.get("ok"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=res.get("detail") or res.get("error") or "Reminder action failed",
        )
    try:
        log_subscription_event(
            conn,
            user_id,
            f"reminder_{body.action}",
            subscription_id=int(res.get("subscription_id") or 0) or None,
            payload={"reminder_id": reminder_id},
        )
    except Exception:
        pass
    return res


@router.patch("/{user_id}/insights/{insight_id}/read")
def patch_insight_read(user_id: int, insight_id: int, conn=Depends(subscription_intel_connection)):
    if not mark_insight_read(conn, user_id, insight_id):
        raise HTTPException(status_code=404, detail="Insight not found")
    return {"ok": True}


@router.post("/{user_id}/reminders/simulate-next-day")
def post_simulate_next_day(user_id: int, conn=Depends(subscription_intel_connection)):
    """Demo helper: shift reminder clocks back 24h (enable with DEMO_MODE=1 in production if desired)."""
    n = simulate_next_day(conn, user_id)
    return {"shifted_rows": n}


@router.post("/{user_id}/reset-demo")
def post_reset_demo(user_id: int, conn=Depends(subscription_intel_connection)):
    """Re-seed intelligence demo data for this user (real DB writes)."""
    from services.subscription_intelligence.seed_demo import run_seed_for_user

    run_seed_for_user(conn, user_id, wipe_device=True)
    return {"ok": True}
