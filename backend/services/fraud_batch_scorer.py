"""
Background fraud scoring — persists risk to ``transactions`` + ``fraud_alerts``.

HTTP handlers only READ scored data (fast). This worker runs the full rules+ML
pipeline after upload without blocking dashboard / FraudShield / insights APIs.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fraud-batch")


def _severity(score: int) -> str:
    if score >= 85:
        return "CRITICAL"
    if score >= 65:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def _persist_transaction_score(
    cur,
    user_id: int,
    txn_id: int,
    risk: int,
    risk_level: str,
    anomaly: bool,
    reason: str | None,
) -> None:
    cur.execute(
        """
        UPDATE transactions
        SET risk_score = %s,
            risk_level = %s,
            anomaly_flag = %s,
            anomaly_reason = %s,
            ml_processed = TRUE
        WHERE id = %s AND user_id = %s;
        """,
        (risk, risk_level, anomaly, reason, txn_id, user_id),
    )


def _upsert_fraud_alert(
    cur,
    user_id: int,
    txn_id: int,
    *,
    pattern: str,
    risk: int,
    amount: float,
    warn: str,
    payee: str,
) -> None:
    cur.execute(
        """
        SELECT id FROM fraud_alerts
        WHERE user_id = %s AND transaction_id = %s
        LIMIT 1;
        """,
        (user_id, txn_id),
    )
    row = cur.fetchone()
    sev = _severity(risk)
    if row:
        cur.execute(
            """
            UPDATE fraud_alerts
            SET pattern_matched = %s, risk_score = %s, amount_at_risk = %s,
                warning_message = %s, severity = %s, merchant_name = %s
            WHERE id = %s AND user_id = %s;
            """,
            (pattern, risk, amount, warn, sev, payee[:255], row[0], user_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO fraud_alerts (
                user_id, transaction_id, pattern_matched, risk_score, amount_at_risk,
                warning_message, hinglish_explanation, user_action, money_saved,
                severity, merchant_name
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', 0, %s, %s);
            """,
            (
                user_id,
                txn_id,
                pattern,
                risk,
                amount,
                warn,
                "",
                sev,
                payee[:255],
            ),
        )


def batch_score_user_transactions(
    user_id: int,
    *,
    document_id: int | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """
    Score debits through rules + hybrid ML (sync path), persist results.
    Runs in a background thread — never call from a request handler directly.
    """
    from db import get_connection
    from routes.fraud_shield import _load_user_history
    from services.fraud_pipeline import score_transaction_sync
    from services.ml_model import ml_detector

    summary: dict[str, Any] = {
        "user_id": user_id,
        "document_id": document_id,
        "processed": 0,
        "high_risk": 0,
        "errors": 0,
    }
    conn = get_connection()
    cur = conn.cursor()
    try:
        try:
            ml_detector.train(user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("batch_score: IF train uid=%s: %s", user_id, exc)

        if document_id is not None:
            cur.execute(
                """
                SELECT id, merchant, description, amount, transaction_date,
                       transaction_time, payment_method, type
                FROM transactions
                WHERE user_id = %s
                  AND uploaded_document_id = %s
                  AND UPPER(type) = 'DEBIT'
                ORDER BY transaction_date DESC, id DESC
                LIMIT %s;
                """,
                (user_id, document_id, limit),
            )
        else:
            cur.execute(
                """
                SELECT id, merchant, description, amount, transaction_date,
                       transaction_time, payment_method, type
                FROM transactions
                WHERE user_id = %s
                  AND UPPER(type) = 'DEBIT'
                  AND (COALESCE(ml_processed, FALSE) = FALSE
                       OR uploaded_document_id IS NOT NULL)
                ORDER BY transaction_date DESC, id DESC
                LIMIT %s;
                """,
                (user_id, limit),
            )
        rows = cur.fetchall()

        for row in rows:
            txn_id = int(row[0])
            payee = (row[1] or row[2] or "").strip()
            amount = float(row[3] or 0)
            td = row[4]
            tt = row[5]
            if isinstance(td, date) and tt is not None:
                at = datetime.combine(td, tt)
            elif isinstance(td, date):
                at = datetime.combine(td, datetime.min.time())
            else:
                at = datetime.now()

            uh = _load_user_history(conn, user_id, payee, at)
            score_tx = {
                "payee": payee,
                "merchant": payee,
                "amount": amount,
                "hour": at.hour,
                "minute": at.minute,
                "description": (row[2] or "")[:200],
                "payment_method": (row[6] or "CARD"),
                "type": "DEBIT",
            }
            try:
                pr = score_transaction_sync(
                    user_id,
                    score_tx,
                    uh,
                    conn=conn,
                    txn_id=txn_id,
                    lightweight=True,
                )
                risk = int(pr.risk_score)
                reason = (
                    pr.risk_factors[0]
                    if pr.risk_factors
                    else (pr.pattern_matched or "FraudShield batch score")
                )
                _persist_transaction_score(
                    cur,
                    user_id,
                    txn_id,
                    risk,
                    pr.risk_level,
                    risk >= 50,
                    reason if risk >= 50 else None,
                )
                if risk >= 50:
                    summary["high_risk"] += 1
                    _upsert_fraud_alert(
                        cur,
                        user_id,
                        txn_id,
                        pattern=str(pr.pattern_matched or "UNUSUAL_TRANSACTION"),
                        risk=risk,
                        amount=amount,
                        warn=str(reason)[:500],
                        payee=payee,
                    )
                summary["processed"] += 1
            except Exception:
                summary["errors"] += 1
                logger.exception("batch_score txn failed uid=%s tid=%s", user_id, txn_id)

        conn.commit()
        logger.info(
            "batch_score done uid=%s processed=%s high_risk=%s errors=%s",
            user_id,
            summary["processed"],
            summary["high_risk"],
            summary["errors"],
        )
    except Exception:
        conn.rollback()
        logger.exception("batch_score_user_transactions failed uid=%s", user_id)
        raise
    finally:
        cur.close()
        conn.close()

    return summary


def _worker(user_id: int, document_id: int | None) -> None:
    try:
        summary = batch_score_user_transactions(user_id, document_id=document_id)
        try:
            from services.async_runner import run_coroutine
            from services.fraud_pipeline import publish_batch_scored
            from services.upload_pipeline import emit_data_updated

            run_coroutine(
                publish_batch_scored(user_id, int(summary.get("processed") or 0)),
                timeout=10,
            )
            emit_data_updated(user_id, "FraudShield")
        except Exception:
            pass
    except Exception:
        logger.exception("fraud batch worker failed uid=%s", user_id)


def schedule_fraud_batch_score(user_id: int, *, document_id: int | None = None) -> None:
    """Queue background scoring (non-blocking). Safe for all users after every import."""
    _executor.submit(_worker, user_id, document_id)
    logger.info("fraud batch scheduled uid=%s document_id=%s", user_id, document_id)
