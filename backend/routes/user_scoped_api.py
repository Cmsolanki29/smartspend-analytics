"""
Global per-user API surface (any user_id from JWT workspace).

Mounted at /api — paths:
  GET /{user_id}/fraud-alerts?mode=
  GET /{user_id}/behaviour?mode=
  GET /{user_id}/investigation?mode=
  GET /{user_id}/linked-accounts
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_db
from services.dashboard_scope import resolve_scope_mode, transaction_scope_sql
from utils.auth import get_current_user_id

router = APIRouter(tags=["user-scoped"])


def _ensure_user_access(requested_user_id: int, jwt_user_id: int) -> None:
    if int(requested_user_id) != int(jwt_user_id):
        raise HTTPException(status_code=403, detail="Access denied for this user")


@router.get("/{user_id}/linked-accounts")
def linked_accounts(
    user_id: int,
    jwt_user_id: int = Depends(get_current_user_id),
    conn=Depends(get_db),
):
    _ensure_user_access(user_id, jwt_user_id)
    from services.dashboard_scope import normalize_dashboard_mode

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(dashboard_mode, 'merged') FROM users WHERE id = %s",
            (user_id,),
        )
        dm_row = cur.fetchone()
        dashboard_mode = normalize_dashboard_mode(str(dm_row[0] if dm_row else "merged"))
        cur.execute(
            """
            SELECT cs.id, cs.source_type, cs.institution_name, cs.account_number_masked,
                   cs.is_primary, cs.status, cs.connected_at, cs.is_visible_on_dashboard,
                   cs.added_via,
                   (SELECT COUNT(DISTINCT ud.id) FROM uploaded_documents ud
                    WHERE ud.connected_source_id = cs.id) AS uploads_count,
                   (SELECT COUNT(DISTINCT t.id) FROM transactions t
                    WHERE t.connected_source_id = cs.id) AS transactions_count
            FROM connected_sources cs
            WHERE cs.user_id = %s
              AND COALESCE(cs.is_ghost, FALSE) = FALSE
              AND cs.status = 'active'
            ORDER BY cs.is_primary DESC, cs.connected_at DESC;
            """,
            (user_id,),
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        if r.get("connected_at"):
            r["connected_at"] = r["connected_at"].isoformat()
    return {"sources": rows, "dashboard_mode": dashboard_mode, "linked_accounts": rows}


@router.get("/{user_id}/fraud-alerts")
def fraud_alerts(
    user_id: int,
    mode: Optional[str] = Query(
        None,
        alias="mode",
        description="bank_only | credit_card_only | merged",
    ),
    scope: Optional[str] = Query(None, description="alias for mode"),
    jwt_user_id: int = Depends(get_current_user_id),
    conn=Depends(get_db),
):
    _ensure_user_access(user_id, jwt_user_id)
    from routes.fraud_shield import list_alerts

    view = mode or scope
    return list_alerts(user_id, severity=None, scope=view, conn=conn)


@router.get("/{user_id}/behaviour")
def behaviour_profile(
    user_id: int,
    mode: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    jwt_user_id: int = Depends(get_current_user_id),
    conn=Depends(get_db),
):
    _ensure_user_access(user_id, jwt_user_id)
    cur = conn.cursor()
    try:
        view = resolve_scope_mode(cur, user_id, mode or scope)
        scope_sql = transaction_scope_sql("t", view)

        cur.execute(
            f"""
            SELECT COALESCE(hour_of_day, EXTRACT(HOUR FROM transaction_time)::int) AS hr,
                   COUNT(*)::int AS cnt
            FROM transactions t
            WHERE t.user_id = %s
              AND t.transaction_date >= (CURRENT_DATE - INTERVAL '90 days')
              AND ({scope_sql})
            GROUP BY hr
            ORDER BY hr;
            """,
            (user_id,),
        )
        hourly_map = {int(r[0]): int(r[1]) for r in cur.fetchall() if r[0] is not None}
        login_patterns = [{"hour": f"{h:02d}", "count": hourly_map.get(h, 0)} for h in range(24)]

        cur.execute(
            f"""
            SELECT COALESCE(t.location, 'Unknown') AS loc,
                   COUNT(*)::int AS cnt,
                   MAX(t.transaction_date) AS last_seen,
                   SUM(CASE WHEN COALESCE(t.anomaly_flag, FALSE) THEN 1 ELSE 0 END)::int AS anomaly_cnt
            FROM transactions t
            WHERE t.user_id = %s
              AND COALESCE(t.location, '') <> ''
              AND ({scope_sql})
            GROUP BY loc
            ORDER BY cnt DESC
            LIMIT 10;
            """,
            (user_id,),
        )
        locations = []
        for loc, cnt, last_seen, anom in cur.fetchall():
            risk = "low"
            if int(anom or 0) >= 3:
                risk = "high"
            elif int(anom or 0) >= 1:
                risk = "medium"
            locations.append(
                {
                    "city": str(loc),
                    "country": "IN",
                    "count": int(cnt),
                    "last_seen": last_seen.isoformat() if last_seen else None,
                    "risk": risk,
                }
            )

        cur.execute(
            f"""
            SELECT t.id, t.merchant, t.amount::float, t.transaction_date,
                   COALESCE(t.risk_score, 0)::int, COALESCE(t.anomaly_reason, '')
            FROM transactions t
            WHERE t.user_id = %s
              AND COALESCE(t.anomaly_flag, FALSE) = TRUE
              AND COALESCE(t.risk_score, 0) >= 50
              AND ({scope_sql})
            ORDER BY t.risk_score DESC, t.transaction_date DESC
            LIMIT 20;
            """,
            (user_id,),
        )
        anomalies = []
        for tid, merchant, amount, tdate, risk, reason in cur.fetchall():
            sev = "high" if int(risk) >= 70 else "medium"
            anomalies.append(
                {
                    "type": "unusual_spend",
                    "severity": sev,
                    "description": reason or f"Unusual spend at {merchant}",
                    "transaction_id": int(tid),
                    "amount": float(amount or 0),
                    "date": tdate.isoformat() if tdate else None,
                }
            )

        cur.execute(
            f"""
            SELECT COALESCE(AVG(t.risk_score), 0)::float,
                   COUNT(*) FILTER (WHERE COALESCE(t.anomaly_flag, FALSE))::int,
                   COUNT(*)::int
            FROM transactions t
            WHERE t.user_id = %s
              AND UPPER(COALESCE(t.type, '')) = 'DEBIT'
              AND t.transaction_date >= (CURRENT_DATE - INTERVAL '90 days')
              AND ({scope_sql});
            """,
            (user_id,),
        )
        avg_risk, anom_cnt, total = cur.fetchone() or (0, 0, 0)
        risk_score = max(0, min(100, int(round(100 - float(avg_risk or 0)))))
        if int(anom_cnt or 0) > 5:
            risk_score = min(risk_score, 40)

        return {
            "user_id": user_id,
            "mode": view,
            "risk_score": risk_score,
            "login_patterns": login_patterns,
            "locations": locations,
            "anomalies": anomalies,
            "recent_activity": [],
            "empty": int(total or 0) == 0,
            "message": (
                "No transactions in this view yet. Upload a statement or link an account."
                if int(total or 0) == 0
                else None
            ),
        }
    finally:
        cur.close()


@router.get("/{user_id}/investigation")
def investigation_list(
    user_id: int,
    mode: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    jwt_user_id: int = Depends(get_current_user_id),
    conn=Depends(get_db),
):
    _ensure_user_access(user_id, jwt_user_id)
    cur = conn.cursor()
    try:
        view = resolve_scope_mode(cur, user_id, mode or scope)
        scope_sql = transaction_scope_sql("t", view)
        cur.execute(
            f"""
            SELECT t.id, COALESCE(t.merchant, t.description, 'Unknown'),
                   t.amount::float, t.transaction_date, t.transaction_time,
                   COALESCE(t.risk_score, 0)::int, COALESCE(t.risk_level, 'LOW'),
                   COALESCE(t.anomaly_reason, ''),
                   COALESCE(a.alert_type, 'ML_ANOMALY')
            FROM transactions t
            LEFT JOIN alerts a ON a.transaction_id = t.id AND a.user_id = t.user_id
            WHERE t.user_id = %s
              AND COALESCE(t.anomaly_flag, FALSE) = TRUE
              AND COALESCE(t.risk_score, 0) >= 50
              AND ({scope_sql})
            ORDER BY t.risk_score DESC, t.transaction_date DESC NULLS LAST, t.id DESC
            LIMIT %s;
            """,
            (user_id, limit),
        )
        items: list[dict[str, Any]] = []
        for row in cur.fetchall():
            alert_type = str(row[8] or "ML_ANOMALY")
            items.append(
                {
                    "transaction_id": int(row[0]),
                    "merchant": row[1],
                    "amount": float(row[2] or 0),
                    "transaction_date": row[3].isoformat() if row[3] else None,
                    "transaction_time": str(row[4]) if row[4] else None,
                    "risk_score": int(row[5] or 0),
                    "risk_level": row[6],
                    "anomaly_reason": row[7],
                    "alert_type": alert_type,
                    "display_label": (
                        "Unusual Spend"
                        if alert_type.upper() == "ML_ANOMALY"
                        else "Fraud Alert"
                    ),
                }
            )
        return {
            "user_id": user_id,
            "mode": view,
            "investigations": items,
            "count": len(items),
            "empty": len(items) == 0,
            "message": (
                "No investigations in this view. Only flagged spends with risk score 50+ appear here."
                if not items
                else None
            ),
        }
    finally:
        cur.close()
