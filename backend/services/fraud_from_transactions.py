"""Score in-scope transactions for FraudShield (no seed/demo alerts)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from services.dashboard_scope import resolve_scope_mode, transaction_scope_sql


def _severity_from_score(score: int) -> str:
    if score >= 85:
        return "CRITICAL"
    if score >= 65:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def _row_to_tx_dict(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "merchant": row[1] or row[2] or "",
        "description": row[2] or "",
        "amount": float(row[3] or 0),
        "transaction_date": row[4],
        "transaction_time": row[5],
        "payment_method": row[6] or "CARD",
        "type": row[7] or "DEBIT",
    }


def score_scoped_transactions(
    cur,
    user_id: int,
    *,
    limit: int = 50,
    min_risk: int = 50,
    days: int = 120,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    mode = resolve_scope_mode(cur, user_id, scope)
    scope_sql = transaction_scope_sql("t", mode)
    since = date.today() - timedelta(days=days)
    cur.execute(
        f"""
        SELECT t.id, t.merchant, t.description, t.amount, t.transaction_date,
               t.transaction_time, t.payment_method, t.type
        FROM transactions t
        WHERE t.user_id = %s
          AND UPPER(t.type) = 'DEBIT'
          AND t.transaction_date >= %s
          AND ({scope_sql})
        ORDER BY t.transaction_date DESC, t.transaction_time DESC NULLS LAST, t.id DESC
        LIMIT %s;
        """,
        (user_id, since, limit),
    )
    rows = cur.fetchall()
    from routes.fraud_shield import _load_user_history
    from services.fraud_pipeline import score_transaction_sync

    conn = cur.connection
    alerts: list[dict[str, Any]] = []
    for row in rows:
        tx = _row_to_tx_dict(row)
        payee = (tx.get("merchant") or tx.get("description") or "").strip()
        td = tx["transaction_date"]
        tt = tx.get("transaction_time")
        if isinstance(td, date) and tt is not None:
            at = datetime.combine(td, tt)
        else:
            at = datetime.now()
        uh = _load_user_history(conn, user_id, payee, at)
        score_tx = {
            "payee": payee,
            "merchant": payee,
            "amount": float(tx.get("amount") or 0),
            "hour": at.hour,
            "minute": at.minute,
            "description": (tx.get("description") or ""),
            "payment_method": (tx.get("payment_method") or "CARD"),
        }
        pr = None
        try:
            pr = score_transaction_sync(
                user_id, score_tx, uh, conn=conn, txn_id=int(tx["id"])
            )
            risk = int(pr.risk_score)
            pattern = pr.pattern_matched or "UNUSUAL_TRANSACTION"
            warn = (
                pr.risk_factors[0]
                if pr.risk_factors
                else (
                    f"Flagged by {', '.join(pr.flagged_by)}"
                    if pr.flagged_by
                    else "Flagged by FraudShield pipeline"
                )
            )
        except Exception:
            from routes.fraud_shield import calculate_fraud_risk_score

            result = calculate_fraud_risk_score(score_tx, uh)
            risk = int(result.get("risk_score") or 0)
            pattern = result.get("pattern_matched") or "UNUSUAL_TRANSACTION"
            warn = (
                (result.get("risk_factors") or ["Unusual transaction"])[0]
                if isinstance(result.get("risk_factors"), list) and result.get("risk_factors")
                else "Flagged by FraudShield rules"
            )
        if risk < min_risk:
            continue
        alerts.append(
            {
                "id": f"txn-{tx['id']}",
                "transaction_id": tx["id"],
                "pattern_matched": pattern,
                "risk_score": risk,
                "amount_at_risk": tx["amount"],
                "warning_message": warn,
                "hinglish_explanation": "",
                "user_action": "PENDING",
                "money_saved": 0.0,
                "created_at": at.isoformat(),
                "severity": _severity_from_score(risk),
                "merchant": payee,
                "source": "transaction",
                "flagged_by": list(pr.flagged_by) if pr else [],
                "models_used": dict(pr.models_used) if pr else {},
            }
        )
    alerts.sort(key=lambda a: (-a["risk_score"], a.get("created_at") or ""))
    return alerts


def scoped_db_fraud_alerts(cur, user_id: int, scope: str | None = None) -> list[dict[str, Any]]:
    """fraud_alerts rows whose transaction is in the current dashboard scope."""
    mode = resolve_scope_mode(cur, user_id, scope)
    scope_sql = transaction_scope_sql("t", mode)
    _sev = """CASE
        WHEN COALESCE(fa.risk_score, 0) >= 85 THEN 'CRITICAL'
        WHEN COALESCE(fa.risk_score, 0) >= 65 THEN 'HIGH'
        WHEN COALESCE(fa.risk_score, 0) >= 35 THEN 'MEDIUM'
        ELSE 'LOW'
    END"""
    cur.execute(
        f"""
        SELECT fa.id, fa.pattern_matched, fa.risk_score, fa.amount_at_risk, fa.warning_message,
               fa.hinglish_explanation, fa.user_action, fa.money_saved, fa.created_at,
               ({_sev}) AS severity, fa.transaction_id,
               COALESCE(t.merchant, t.description, '')
        FROM fraud_alerts fa
        INNER JOIN transactions t ON t.id = fa.transaction_id AND t.user_id = fa.user_id
        WHERE fa.user_id = %s AND ({scope_sql})
        ORDER BY fa.risk_score DESC NULLS LAST, fa.created_at DESC;
        """,
        (user_id,),
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": r[0],
                "pattern_matched": r[1],
                "risk_score": int(r[2] or 0),
                "amount_at_risk": float(r[3] or 0),
                "warning_message": r[4],
                "hinglish_explanation": r[5],
                "user_action": r[6],
                "money_saved": float(r[7] or 0),
                "created_at": r[8].isoformat() if r[8] else None,
                "severity": r[9] or "MEDIUM",
                "transaction_id": r[10],
                "merchant": r[11] or "",
                "source": "fraud_alerts",
            }
        )
    return out


def alerts_from_stored_transaction_scores(
    cur,
    user_id: int,
    *,
    limit: int = 50,
    min_risk: int = 50,
    days: int = 120,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fast path: use risk_score / anomaly_flag already on transactions (upload heuristics).
    No live hybrid_scorer — avoids 500s when the API is under load.
    """
    mode = resolve_scope_mode(cur, user_id, scope)
    scope_sql = transaction_scope_sql("t", mode)
    since = date.today() - timedelta(days=days)
    cur.execute(
        f"""
        SELECT t.id, t.merchant, t.description, t.amount, t.transaction_date,
               t.transaction_time, COALESCE(t.risk_score, 0)::int,
               t.anomaly_reason, COALESCE(t.anomaly_flag, FALSE)
        FROM transactions t
        WHERE t.user_id = %s
          AND UPPER(t.type) = 'DEBIT'
          AND t.transaction_date >= %s
          AND ({scope_sql})
          AND (
            COALESCE(t.anomaly_flag, FALSE) = TRUE
            OR COALESCE(t.risk_score, 0) >= %s
          )
        ORDER BY t.transaction_date DESC, t.transaction_time DESC NULLS LAST, t.id DESC
        LIMIT %s;
        """,
        (user_id, since, min_risk, limit),
    )
    alerts: list[dict[str, Any]] = []
    for row in cur.fetchall():
        risk = int(row[6] or 0)
        if risk < min_risk:
            continue
        tx = {
            "id": row[0],
            "merchant": row[1] or row[2] or "",
            "description": row[2] or "",
            "amount": float(row[3] or 0),
            "transaction_date": row[4],
            "transaction_time": row[5],
            "payment_method": "CARD",
            "type": "DEBIT",
        }
        payee = (tx.get("merchant") or tx.get("description") or "").strip()
        td = tx["transaction_date"]
        tt = tx.get("transaction_time")
        if isinstance(td, date) and tt is not None:
            at = datetime.combine(td, tt)
        else:
            at = datetime.now()
        reason = (row[7] or "").strip() or "Flagged from stored risk score"
        pattern = "ANOMALY_FLAG" if row[8] else "STORED_RISK_SCORE"
        alerts.append(
            {
                "id": f"txn-{tx['id']}",
                "transaction_id": tx["id"],
                "pattern_matched": pattern,
                "risk_score": risk,
                "amount_at_risk": tx["amount"],
                "warning_message": reason,
                "hinglish_explanation": "",
                "user_action": "PENDING",
                "money_saved": 0.0,
                "created_at": at.isoformat(),
                "severity": _severity_from_score(risk),
                "merchant": payee,
                "source": "transaction_stored",
                "flagged_by": [],
                "models_used": {},
            }
        )
    alerts.sort(key=lambda a: (-a["risk_score"], a.get("created_at") or ""))
    return alerts


def get_merged_fraud_alerts(
    cur,
    user_id: int,
    scope: str | None = None,
    *,
    limit: int = 50,
    min_risk: int = 50,
) -> list[dict[str, Any]]:
    """
    Read scored fraud signals from DB (written by ``fraud_batch_scorer``).
    Never runs live ML inside HTTP handlers — stable for every user.
    """
    db_alerts = scoped_db_fraud_alerts(cur, user_id, scope)
    txn_alerts = alerts_from_stored_transaction_scores(
        cur, user_id, limit=limit, min_risk=min_risk, scope=scope
    )
    return merge_alerts(db_alerts, txn_alerts)


def get_live_events_from_db(
    cur,
    user_id: int,
    *,
    limit: int = 20,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    """Recent scored debits for the live feed (DB read only)."""
    alerts = alerts_from_stored_transaction_scores(
        cur, user_id, limit=limit, min_risk=0, scope=scope
    )
    events = []
    for a in alerts:
        risk = int(a.get("risk_score") or 0)
        if risk >= 65:
            st = "BLOCKED"
        elif risk >= 35:
            st = "REVIEW"
        else:
            st = "APPROVED"
        events.append(
            {
                "id": a.get("id"),
                "transaction_id": a.get("transaction_id"),
                "merchant": a.get("merchant") or a.get("pattern_matched"),
                "amount": a.get("amount_at_risk"),
                "status": st,
                "score": risk,
                "ts": a.get("created_at"),
            }
        )
    return events


def merge_alerts(db_alerts: list[dict], txn_alerts: list[dict]) -> list[dict]:
    seen_txn: set[int] = set()
    merged: list[dict] = []
    for a in db_alerts:
        tid = a.get("transaction_id")
        if tid is not None:
            seen_txn.add(int(tid))
        merged.append(a)
    for a in txn_alerts:
        tid = a.get("transaction_id")
        if tid is not None and int(tid) in seen_txn:
            continue
        merged.append(a)
    merged.sort(key=lambda x: (-int(x.get("risk_score") or 0), x.get("created_at") or ""))
    return merged
