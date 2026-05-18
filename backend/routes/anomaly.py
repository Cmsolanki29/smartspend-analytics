"""Anomaly routes: ML detection, stats, patterns, and alerts."""

from __future__ import annotations

import time
from collections import Counter
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_db
from models.schemas import AnomalyResponse
from services.dashboard_scope import resolve_scope_mode, transaction_scope_sql
from services.ml_model import ml_detector
from services.pattern_analyzer import pattern_analyzer

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("/{user_id}/patterns")
def get_patterns(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
        if not cur.fetchone():
            raise HTTPException(404, "User not found")
    finally:
        cur.close()
    return {
        "spending_velocity": pattern_analyzer.analyze_spending_velocity(user_id),
        "recurring_transactions": pattern_analyzer.find_recurring_transactions(user_id),
        "category_spikes": pattern_analyzer.detect_category_spikes(user_id),
        "merchant_frequency": pattern_analyzer.get_merchant_frequency(user_id, 10),
        "time_patterns": pattern_analyzer.analyze_time_patterns(user_id),
        "savings_trajectory": pattern_analyzer.get_savings_trajectory(user_id),
    }


@router.get("/{user_id}/alerts")
def get_and_mark_alerts_read(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, severity, alert_type, message, detail, created_at
            FROM alerts
            WHERE user_id = %s AND is_read = FALSE
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        ids = [r[0] for r in rows]
        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(f"UPDATE alerts SET is_read = TRUE WHERE id IN ({placeholders})", ids)
        return {
            "count": len(rows),
            "alerts": [
                {
                    "id": r[0],
                    "severity": r[1],
                    "alert_type": r[2],
                    "message": r[3],
                    "detail": r[4],
                    "created_at": str(r[5]),
                }
                for r in rows
            ],
        }
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()


@router.get("/{user_id}/stats")
def anomaly_stats_enhanced(
    user_id: int,
    scope: Optional[str] = Query(
        None,
        description="bank_only | credit_card_only | merged",
    ),
    conn=Depends(get_db),
):
    cur = conn.cursor()
    try:
        mode = resolve_scope_mode(cur, user_id, scope)
        scope_sql = transaction_scope_sql("t", mode)
        cur.execute(
            f"""
            SELECT COALESCE(t.anomaly_reason, 'UNKNOWN'), t.risk_level, t.risk_score, t.merchant, t.amount
            FROM transactions t
            WHERE t.user_id = %s AND t.anomaly_flag = TRUE
              AND ({scope_sql});
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        types_counter: Counter[str] = Counter()
        risk_counter: Counter[str] = Counter()
        bucket = Counter()
        risky_merchant_amt: dict[str, float] = {}
        total_at_risk = 0.0

        for reason, level, rscore, merchant, amount in rows:
            atype = reason.split(":", 1)[0].strip() if reason and ":" in reason else "UNSPECIFIED"
            types_counter[atype] += 1
            risk_counter[level or "LOW"] += 1
            rs = int(rscore or 0)
            if rs <= 30:
                bucket["0-30"] += 1
            elif rs <= 60:
                bucket["31-60"] += 1
            elif rs <= 85:
                bucket["61-85"] += 1
            else:
                bucket["86-100"] += 1
            amt = float(amount or 0)
            if level in ("HIGH", "CRITICAL"):
                total_at_risk += amt
            m = merchant or "Unknown"
            risky_merchant_amt[m] = risky_merchant_amt.get(m, 0.0) + amt

        most_risky = (
            max(risky_merchant_amt, key=risky_merchant_amt.get) if risky_merchant_amt else None
        )

        return {
            "total_anomalies": len(rows),
            "high_risk_count": int(
                risk_counter.get("HIGH", 0) + risk_counter.get("CRITICAL", 0)
            ),
            "by_type": dict(types_counter),
            "by_severity": dict(risk_counter),
            "risk_score_distribution": dict(bucket),
            "most_risky_merchant": most_risky,
            "total_amount_at_risk": round(total_at_risk, 2),
        }
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()


@router.post("/{user_id}/run-detection")
def run_detection(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
        if not cur.fetchone():
            raise HTTPException(404, "User not found")
    finally:
        cur.close()

    t0 = time.perf_counter()
    ml_detector.train(user_id)
    det = ml_detector.detect_and_update(user_id, process_all=False)
    ms = int((time.perf_counter() - t0) * 1000)
    return {
        "processed": det.get("processed", 0),
        "anomalies_found": det.get("anomalies_found", 0),
        "high_risk": det.get("high_risk", 0),
        "duration_ms": ms,
        "error": det.get("error"),
    }


@router.get("/{user_id}", response_model=list[AnomalyResponse])
def list_anomalies(
    user_id: int,
    severity: Optional[str] = Query(
        None, description="Optional filter: LOW, MEDIUM, HIGH, or CRITICAL"
    ),
    limit: int = Query(20, ge=1, le=200),
    scope: Optional[str] = Query(
        None,
        description="bank_only | credit_card_only | merged",
    ),
    conn=Depends(get_db),
):
    if severity and severity.upper() not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        raise HTTPException(400, "severity must be LOW, MEDIUM, HIGH, or CRITICAL")
    cur = conn.cursor()
    try:
        mode = resolve_scope_mode(cur, user_id, scope)
        scope_sql = transaction_scope_sql("t", mode)
        q = f"""
            SELECT t.id, t.merchant, t.amount, t.transaction_date, COALESCE(t.anomaly_reason, ''),
                   t.risk_score, t.risk_level
            FROM transactions t
            WHERE t.user_id = %s AND t.anomaly_flag = TRUE
              AND ({scope_sql})
        """
        params: list[Any] = [user_id]
        if severity:
            q += " AND risk_level = %s"
            params.append(severity.upper())
        q += " ORDER BY risk_score DESC, transaction_date DESC LIMIT %s"
        params.append(limit)
        cur.execute(q, params)
        out = []
        for r in cur.fetchall():
            reason = r[4] or ""
            atype = reason.split(":", 1)[0].strip() if ":" in reason else "ANOMALY"
            out.append(
                AnomalyResponse(
                    transaction_id=r[0],
                    merchant=r[1] or "",
                    amount=float(r[2]),
                    transaction_date=r[3],
                    anomaly_type=atype[:80],
                    risk_score=int(r[5] or 0),
                    risk_level=r[6] or "LOW",
                    reason=reason or "Flagged by rules or ML",
                )
            )
        return out
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()
