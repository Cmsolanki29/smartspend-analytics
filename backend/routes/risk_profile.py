"""
routes/risk_profile.py — Phase 2, 6, 8 user-facing risk profile endpoints.

Three endpoints that make Behavior Profile, Device Trust, and Feedback Stats
pages work with real data instead of demo data.

Auth: Optional Bearer JWT.  All endpoints also work without auth in dev mode
      so the frontend riskClient (which sends JWT) doesn't get 401 errors.

Mounted under /api in main.py  →  full paths:
    GET /api/risk/users/{user_id}/behavior-profile
    GET /api/risk/users/{user_id}/devices
    GET /api/risk/users/{user_id}/feedback-stats
"""

from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from core.db import get_pool
from core.config import get_settings
from schemas.feedback import ReviewDecision
from services.dashboard_scope import normalize_dashboard_mode, transaction_scope_sql
from utils.auth import get_current_user_id

router = APIRouter(prefix="/risk", tags=["risk-profile"])

_BACKEND_DIR = Path(__file__).resolve().parent.parent


# ── helpers ────────────────────────────────────────────────────────────────

def _action_from_score(score: float) -> str:
    if score >= 70:
        return "block"
    if score >= 50:
        return "challenge"
    if score >= 30:
        return "review"
    return "allow"


def _device_type_from_method(method: str) -> str:
    m = (method or "").lower()
    if "upi" in m:
        return "mobile"
    if "card" in m or "credit" in m or "debit" in m:
        return "card"
    if "net" in m or "netbanking" in m:
        return "desktop"
    if "cash" in m:
        return "cash"
    return "mobile"


# ── Behavior Profile ──────────────────────────────────────────────────────

@router.get("/users/{user_id}/behavior-profile")
async def get_behavior_profile(
    user_id: int,
    scope: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """
    Phase 2 — Feature Store: user behavioural risk profile.
    Aggregates transaction history into login patterns, location analysis,
    anomaly list, and a composite risk score.
    """
    try:
        pool = get_pool()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database pool not available")

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    async with pool.acquire() as conn:
        if scope or mode:
            view = normalize_dashboard_mode(scope or mode)
        else:
            mode_row = await conn.fetchrow(
                "SELECT COALESCE(dashboard_mode, 'merged') FROM users WHERE id = $1",
                user_id,
            )
            view = normalize_dashboard_mode(str(mode_row[0]) if mode_row else "merged")
        scope_sql = transaction_scope_sql("t", view)

        # 1. Hourly activity distribution (24 buckets)
        hourly_rows = await conn.fetch(
            f"""
            SELECT COALESCE(hour_of_day, EXTRACT(HOUR FROM transaction_time)::int) AS hr,
                   COUNT(*) AS cnt
            FROM transactions t
            WHERE t.user_id = $1 AND t.transaction_date >= $2::date
              AND ({scope_sql})
            GROUP BY hr
            ORDER BY hr
            """,
            user_id, cutoff.date(),
        )
        hourly_map = {r["hr"]: int(r["cnt"]) for r in hourly_rows}
        login_patterns = [
            {"hour": f"{h:02d}", "count": hourly_map.get(h, 0)}
            for h in range(24)
        ]

        # 2. Distinct locations with risk flags
        loc_rows = await conn.fetch(
            f"""
            SELECT location,
                   COUNT(*)                                     AS cnt,
                   MAX(transaction_date)                        AS last_seen,
                   SUM(CASE WHEN anomaly_flag THEN 1 ELSE 0 END) AS anomaly_cnt
            FROM transactions t
            WHERE t.user_id = $1 AND t.location IS NOT NULL AND t.location != ''
              AND ({scope_sql})
            GROUP BY location
            ORDER BY cnt DESC
            LIMIT 10
            """,
            user_id,
        )
        locations = []
        for i, r in enumerate(loc_rows):
            ratio = (r["anomaly_cnt"] or 0) / max(r["cnt"], 1)
            risk  = "high" if ratio > 0.2 else ("medium" if i > 1 or ratio > 0.05 else "low")
            loc_str = str(r["location"])
            parts   = [p.strip() for p in loc_str.split(",")]
            city    = parts[0] if parts else loc_str
            country = parts[-1].strip() if len(parts) > 1 else "IN"
            locations.append({
                "city":      city,
                "country":   country[:10],
                "count":     int(r["cnt"]),
                "risk":      risk,
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            })

        # 3. Detected anomalies
        anom_rows = await conn.fetch(
            f"""
            SELECT id, merchant, amount, transaction_date, transaction_time,
                   risk_level, anomaly_reason
            FROM transactions t
            WHERE t.user_id = $1 AND t.anomaly_flag = TRUE
              AND ({scope_sql})
            ORDER BY transaction_date DESC, transaction_time DESC
            LIMIT 20
            """,
            user_id,
        )
        anomalies = []
        for r in anom_rows:
            lvl = str(r["risk_level"] or "LOW").upper()
            severity = "high" if lvl in ("CRITICAL", "HIGH") else ("medium" if lvl == "MEDIUM" else "low")
            reason   = r["anomaly_reason"] or "Unusual transaction pattern"
            ts = datetime.combine(r["transaction_date"], r["transaction_time"])
            anomalies.append({
                "id":          r["id"],
                "type":        "anomaly",
                "description": f"{reason[:80]} — {r['merchant'] or 'Unknown merchant'}",
                "severity":    severity,
                "ts":          ts.isoformat(),
            })

        # 4. Recent activity timeline (last 10 transactions)
        recent_rows = await conn.fetch(
            f"""
            SELECT id, merchant, amount, payment_method,
                   transaction_date, transaction_time, anomaly_flag, type
            FROM transactions t
            WHERE t.user_id = $1
              AND ({scope_sql})
            ORDER BY transaction_date DESC, transaction_time DESC
            LIMIT 10
            """,
            user_id,
        )
        recent_activity = []
        for r in recent_rows:
            ts = datetime.combine(r["transaction_date"], r["transaction_time"])
            method  = r["payment_method"] or "Unknown"
            amount  = float(r["amount"] or 0)
            action  = "Transaction" if r["type"] == "DEBIT" else "Credit"
            label   = f"{action} ₹{int(amount):,}" + (f" — {r['merchant']}" if r["merchant"] else "")
            recent_activity.append({
                "id":      r["id"],
                "action":  label,
                "channel": method,
                "ts":      ts.isoformat(),
                "ok":      not r["anomaly_flag"],
            })

        # 5. Composite risk score
        stats = await conn.fetchrow(
            f"""
            SELECT AVG(risk_score)::float                        AS avg_score,
                   SUM(CASE WHEN anomaly_flag THEN 1 ELSE 0 END) AS anom_count,
                   COUNT(*)                                       AS total
            FROM transactions t
            WHERE t.user_id = $1 AND t.transaction_date >= $2::date
              AND ({scope_sql})
            """,
            user_id, cutoff.date(),
        )
        avg_rs  = float(stats["avg_score"] or 0)
        anom_n  = int(stats["anom_count"] or 0)
        total   = int(stats["total"] or 1)
        # Blend raw avg risk + anomaly rate penalty
        anomaly_rate  = anom_n / max(total, 1)
        risk_score_01 = min((avg_rs / 100) * 0.6 + anomaly_rate * 0.4, 1.0)
        risk_score_pct = round(risk_score_01 * 100, 1)
        risk_action    = _action_from_score(risk_score_pct)

    return {
        "user_id":        user_id,
        "risk_score":     risk_score_01,          # 0-1 for gauge
        "risk_score_pct": risk_score_pct,          # 0-100 human readable
        "risk_action":    risk_action,
        "login_patterns": login_patterns,
        "locations":      locations,
        "anomalies":      anomalies,
        "recent_activity": recent_activity,
        "summary": {
            "total_transactions": total,
            "anomaly_count":      anom_n,
            "anomaly_rate_pct":   round(anomaly_rate * 100, 1),
            "avg_risk_score":     round(avg_rs, 1),
        },
    }


# ── Device Trust ──────────────────────────────────────────────────────────

@router.get("/users/{user_id}/devices")
async def get_devices(user_id: int) -> dict[str, Any]:
    """
    Phase 6 — Graph Intelligence: device/channel trust profile.
    Derives a "device" from each unique payment_method+location combo,
    scores trust by usage frequency and anomaly rate.
    """
    try:
        pool = get_pool()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database pool not available")

    async with pool.acquire() as conn:
        mode_row = await conn.fetchrow(
            "SELECT COALESCE(dashboard_mode, 'merged') FROM users WHERE id = $1",
            user_id,
        )
        mode = normalize_dashboard_mode(str(mode_row[0]) if mode_row else "merged")
        scope_sql = transaction_scope_sql("t", mode)
        rows = await conn.fetch(
            f"""
            SELECT payment_method,
                   location,
                   COUNT(*)                                      AS uses,
                   MIN(transaction_date)                         AS first_seen,
                   MAX(transaction_date)                         AS last_seen,
                   SUM(CASE WHEN anomaly_flag THEN 1 ELSE 0 END) AS anom_count,
                   AVG(risk_score)::float                        AS avg_risk
            FROM transactions t
            WHERE t.user_id = $1 AND t.payment_method IS NOT NULL
              AND ({scope_sql})
            GROUP BY payment_method, location
            ORDER BY uses DESC
            LIMIT 12
            """,
            user_id,
        )

    devices = []
    for i, r in enumerate(rows):
        method    = r["payment_method"] or "Unknown"
        location  = r["location"] or "Unknown"
        uses      = int(r["uses"] or 0)
        anom      = int(r["anom_count"] or 0)
        avg_risk  = float(r["avg_risk"] or 0)
        first     = r["first_seen"]
        last      = r["last_seen"]

        # Trust score: high usage + low anomaly → high trust
        anom_rate   = anom / max(uses, 1)
        trust_score = max(0, min(100, round(100 - avg_risk - anom_rate * 40)))

        if trust_score >= 80:
            status = "trusted"
        elif trust_score >= 50:
            status = "review"
        else:
            status = "alert"

        risk_flags = []
        if i == 0 and uses == 1:
            risk_flags.append("new_device")
        if anom_rate > 0.15:
            risk_flags.append("high_velocity" if uses > 10 else "anomaly_pattern")
        if "SG" in location or "US" in location or "UK" in location:
            risk_flags.append("new_location")
        if uses <= 2:
            risk_flags.append("infrequent_use")

        devices.append({
            "id":          f"dev-{user_id}-{i}",
            "name":        f"{method} — {location[:30]}" if location and location != "Unknown" else method,
            "type":        _device_type_from_method(method),
            "os":          "—",
            "browser":     method,
            "trust_score": trust_score / 100,
            "trust_score_pct": trust_score,
            "status":      status,
            "last_seen":   last.isoformat() if last else None,
            "first_seen":  first.isoformat() if first else None,
            "location":    location,
            "risk_flags":  risk_flags,
            "uses":        uses,
            "txn_count":   uses,
            "avg_amount":  None,
        })

    total     = len(devices)
    trusted   = sum(1 for d in devices if d["status"] == "trusted")
    alerts    = sum(1 for d in devices if d["status"] == "alert")
    avg_trust = round(sum(d["trust_score_pct"] for d in devices) / max(total, 1))

    return {
        "user_id":   user_id,
        "devices":   devices,
        "summary": {
            "total":     total,
            "trusted":   trusted,
            "alerts":    alerts,
            "avg_trust": avg_trust,
        },
    }


# ── Feedback Stats ────────────────────────────────────────────────────────

@router.get("/users/{user_id}/feedback-stats")
async def get_feedback_stats(user_id: int) -> dict[str, Any]:
    """
    Phase 8 — Feedback Flywheel: aggregated fraud report stats for a user.
    Shows how many reports the user filed, how many were confirmed, and the
    estimated model improvement from their labels.
    """
    try:
        pool = get_pool()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database pool not available")

    async with pool.acquire() as conn:
        stats = await conn.fetchrow(
            """
            SELECT
                COUNT(rq.id)                                                    AS total_reports,
                SUM(CASE WHEN rq.resolution = 'fraud'       THEN 1 ELSE 0 END) AS confirmed_fraud,
                SUM(CASE WHEN rq.resolution = 'legitimate'  THEN 1 ELSE 0 END) AS dismissed,
                SUM(CASE WHEN rq.status     = 'pending'     THEN 1 ELSE 0 END) AS pending_review,
                SUM(CASE WHEN rq.status     = 'resolved'    THEN 1 ELSE 0 END) AS resolved_count
            FROM review_queue rq
            JOIN transactions t ON rq.transaction_id = t.id
            WHERE t.user_id = $1
            """,
            user_id,
        )

        # Also get user-reported fraud count from transactions directly
        txn_stats = await conn.fetchrow(
            """
            SELECT
                SUM(CASE WHEN anomaly_flag AND risk_level IN ('HIGH','CRITICAL') THEN 1 ELSE 0 END) AS high_risk_count,
                COUNT(*) AS total_txns
            FROM transactions WHERE user_id = $1
            """,
            user_id,
        )

    total    = int(stats["total_reports"]   or 0)
    fraud    = int(stats["confirmed_fraud"] or 0)
    pending  = int(stats["pending_review"]  or 0)
    resolved = int(stats["resolved_count"]  or 0)

    # Estimate model improvement: each confirmed label ≈ 0.001 AUC delta
    accuracy_delta = round(fraud * 0.0008, 4)

    return {
        "user_id":        user_id,
        "total_reports":  total,
        "confirmed_fraud": fraud,
        "dismissed":      int(stats["dismissed"] or 0),
        "pending_review": pending,
        "resolved_count": resolved,
        "accuracy_delta": accuracy_delta,
        "high_risk_transactions": int(txn_stats["high_risk_count"] or 0),
        "total_transactions":     int(txn_stats["total_txns"] or 0),
    }


# ── Enriched Review Queue ─────────────────────────────────────────────────

@router.get("/review-queue")
async def get_enriched_review_queue(
    status: str = "pending",
    limit: int = 20,
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    Phase 8 — Enriched review queue with transaction details joined in.
    Unlike /admin/review-queue this returns merchant, amount, anomaly_reason
    so the frontend can show meaningful item cards without extra fetches.
    """
    try:
        pool = get_pool()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database pool not available")

    valid = {"pending", "in_review", "resolved", "all"}
    if status not in valid:
        status = "pending"

    async with pool.acquire() as conn:
        params: list[Any] = [limit]
        clauses = []
        if status != "all":
            clauses.append(f"rq.status = ${len(params) + 1}")
            params.append(status)
        if user_id is not None:
            clauses.append(f"t.user_id = ${len(params) + 1}")
            params.append(user_id)
            mode_row = await conn.fetchrow(
                "SELECT COALESCE(dashboard_mode, 'merged') FROM users WHERE id = $1",
                user_id,
            )
            mode = normalize_dashboard_mode(str(mode_row[0]) if mode_row else "merged")
            scope = transaction_scope_sql("t", mode)
            clauses.append(f"({scope})")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = await conn.fetch(
            f"""
            SELECT
                rq.id, rq.transaction_id, rq.score, rq.status, rq.priority,
                rq.resolution, rq.created_at, rq.resolved_at, rq.notes,
                t.merchant, t.amount, t.payment_method, t.category,
                t.anomaly_reason, t.risk_level, t.transaction_date,
                t.user_id
            FROM review_queue rq
            JOIN transactions t ON rq.transaction_id = t.id
            {where}
            ORDER BY rq.priority DESC, rq.score DESC, rq.created_at DESC
            LIMIT $1
            """,
            *params,
        )

    items = []
    for r in rows:
        items.append({
            "id":               str(r["id"]),
            "transaction_id":   r["transaction_id"],
            "txn_ref":          f"TXN-{r['transaction_id']}",
            "score":            r["score"],
            "status":           r["status"],
            "priority":         r["priority"],
            "resolution":       r["resolution"],
            "created_at":       r["created_at"].isoformat() if r["created_at"] else None,
            "resolved_at":      r["resolved_at"].isoformat() if r["resolved_at"] else None,
            "notes":            r["notes"] or r["anomaly_reason"] or "",
            "merchant":         r["merchant"] or "Unknown Merchant",
            "amount":           float(r["amount"] or 0),
            "payment_method":   r["payment_method"] or "—",
            "category":         r["category"] or "—",
            "anomaly_reason":   r["anomaly_reason"] or "",
            "risk_level":       r["risk_level"] or "MEDIUM",
            "transaction_date": r["transaction_date"].isoformat() if r["transaction_date"] else None,
            "user_id":          r["user_id"],
        })

    return {
        "total":  len(items),
        "status": status,
        "items":  items,
    }


@router.post("/review-queue/{queue_id}/self-resolve")
async def self_resolve_review_queue(
    queue_id: UUID,
    body: ReviewDecision,
    auth_user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Resolve a pending review-queue row for the signed-in user (no admin token)."""
    if body.resolution not in ("fraud", "legitimate"):
        raise HTTPException(
            status_code=400,
            detail="resolution must be fraud or legitimate for self-service",
        )
    try:
        pool = get_pool()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    async with pool.acquire() as conn:
        rq = await conn.fetchrow(
            """
            SELECT rq.id, rq.status, t.user_id
            FROM review_queue rq
            JOIN transactions t ON t.id = rq.transaction_id
            WHERE rq.id = $1
            """,
            queue_id,
        )
    if rq is None:
        raise HTTPException(status_code=404, detail="Queue item not found")
    if int(rq["user_id"]) != auth_user_id:
        raise HTTPException(status_code=403, detail="Not your queue item")
    if rq["status"] == "resolved":
        return {"acknowledged": True, "queue_id": str(queue_id), "resolution": body.resolution, "note": "already resolved"}

    from services.feedback.feedback_service import feedback_service  # noqa: PLC0415

    await feedback_service.record_analyst_decision(
        queue_id=queue_id,
        resolution=body.resolution,
        reviewer_id=None,
        notes=(body.notes or "").strip() or "self-service (FraudShield)",
    )
    return {
        "acknowledged": True,
        "queue_id": str(queue_id),
        "resolution": body.resolution,
    }


# ── Model Status ──────────────────────────────────────────────────────────

@router.get("/model-status")
async def get_model_status() -> dict[str, Any]:
    """
    Returns the current trained model's metadata and evaluation metrics.
    Reads from the JSON sidecar saved by bootstrap_train.py.
    Used by the AIPerformance frontend to show real model metrics
    even when MLflow registry is empty.
    """
    settings = get_settings()
    model_path = _BACKEND_DIR / settings.SUPERVISED_MODEL_PATH
    metrics_stem = model_path.stem + "_metrics.json"
    metrics_path = model_path.parent / metrics_stem

    model_exists = model_path.exists()
    metrics: dict[str, Any] = {}

    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            metrics = {}

    return {
        "has_supervised": model_exists,
        "model_path":     str(settings.SUPERVISED_MODEL_PATH),
        "metrics":        metrics,
        "metrics_available": bool(metrics),
    }
