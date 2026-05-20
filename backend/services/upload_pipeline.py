"""
Unified post-import pipeline — runs for every user after statement/CSV ingest.

Phase 1: steps 5–11 after parse+upsert (enrichment at insert via transaction_upsert).
Phase 2+: merchant trust rule, stricter ML gates.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def emit_data_updated(user_id: int, source_name: str) -> None:
    """Notify this user's WebSocket room + log (frontend also uses upload response)."""
    from services.realtime_hub import emit_data_updated_sync

    emit_data_updated_sync(user_id, source_name)
    logger.info("data_updated user_id=%s source=%s", user_id, source_name)


def _persist_dark_patterns(conn, user_id: int, scope: str | None = "merged") -> dict[str, Any]:
    from routes.dark_patterns import _detect_patterns

    result = _detect_patterns(conn, user_id, scope)
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM dark_patterns WHERE user_id = %s AND status <> 'RESOLVED';",
            (user_id,),
        )
        for p in result.get("patterns") or []:
            cur.execute(
                """
                INSERT INTO dark_patterns (
                    user_id, merchant, pattern_type, description, amount_involved,
                    potential_loss, detected_date, evidence, status, action_taken
                )
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE, %s::jsonb, 'ACTIVE', %s);
                """,
                (
                    user_id,
                    p["merchant"],
                    p["pattern_type"],
                    p["description"],
                    p.get("amount_involved", 0),
                    p.get("potential_loss", 0),
                    json.dumps(p.get("evidence", {})),
                    p.get("action", ""),
                ),
            )
    finally:
        cur.close()
    return {
        "patterns_found": int(result.get("total_dark_patterns") or 0),
        "critical_count": int(result.get("critical_count") or 0),
    }


def _detect_emi_patterns(conn, user_id: int, scope: str | None = "merged") -> dict[str, Any]:
    from routes.emi_detector import _build_emi_detection

    report = _build_emi_detection(conn, user_id, scope)
    emis = report.get("emis_detected") or report.get("emis") or []
    return {"emi_count": len(emis) if isinstance(emis, list) else 0}


def _retrain_ml_if_ready(user_id: int, conn) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COUNT(*)::int FROM transactions
            WHERE user_id = %s AND UPPER(type) = 'DEBIT';
            """,
            (user_id,),
        )
        debit_count = int((cur.fetchone() or [0])[0] or 0)
    finally:
        cur.close()
    if debit_count < 30:
        return False
    try:
        from services.ml_model import ml_detector

        return bool(ml_detector.train(user_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("retrain_ml_if_ready failed uid=%s: %s", user_id, exc)
        return False


def _recalculate_health_score(conn, user_id: int, date_range: str | dict | None = None) -> None:
    from services.transaction_enrichment import sync_all_monthly_summaries_for_user

    sync_all_monthly_summaries_for_user(conn, user_id)


def run_post_import_pipeline_light(
    user_id: int,
    conn,
    *,
    source_name: str = "Statement",
    date_range: dict | None = None,
) -> dict[str, Any]:
    """
    Fast path after upload (~2–5s): monthly summaries + dashboard refresh only.
    Fraud ML / dark patterns / EMI run in background via ``run_post_import_pipeline``.
    """
    summary: dict[str, Any] = {"user_id": user_id, "source_name": source_name, "mode": "light"}
    try:
        from services.upload_amount_sanity import verify_user_ledger_after_import

        summary["ledger_sanity"] = verify_user_ledger_after_import(conn, user_id)
    except Exception:
        logger.exception("ledger sanity check failed user_id=%s", user_id)
        summary["ledger_sanity"] = {"repaired_rows": 0}
    try:
        _recalculate_health_score(conn, user_id, date_range)
        summary["health_synced"] = True
    except Exception:
        logger.exception("light health sync failed user_id=%s", user_id)
        summary["health_synced"] = False
    emit_data_updated(user_id, source_name)
    summary["data_updated"] = True
    return summary


def run_post_import_pipeline(
    user_id: int,
    conn,
    *,
    source_name: str = "Statement",
    scope: str | None = "merged",
    date_range: dict | None = None,
    purge_orphans: bool = True,
    document_id: int | None = None,
    skip_heavy_ml: bool = False,
) -> dict[str, Any]:
    """
    Steps 5–11 after transactions are upserted (steps 2–4 run in transaction_upsert).
    """
    if skip_heavy_ml:
        return run_post_import_pipeline_light(user_id, conn, source_name=source_name, date_range=date_range)

    summary: dict[str, Any] = {
        "user_id": user_id,
        "source_name": source_name,
        "orphan_transactions_purged": 0,
    }

    if purge_orphans:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                DELETE FROM transactions
                WHERE user_id = %s AND connected_source_id IS NULL;
                """,
                (user_id,),
            )
            summary["orphan_transactions_purged"] = int(cur.rowcount or 0)
        finally:
            cur.close()

    try:
        from datetime import date as _date

        from services.financial_engine import recalculate_financial_state
        from services.openai_service import invalidate_insight_cache

        today = _date.today()
        invalidate_insight_cache(conn, user_id, today.month, today.year)
        try:
            from services.ai_context_service import invalidate_user_ai_context_cache

            invalidate_user_ai_context_cache(user_id)
        except Exception as cache_exc:  # noqa: BLE001
            logger.warning("ai context cache invalidate failed uid=%s: %s", user_id, cache_exc)
        recalculate_financial_state(
            conn,
            user_id,
            trigger_type="statement_upload",
            trigger_id=document_id,
            trigger_summary=f"Imported data from {source_name}",
        )
        from services.scorer import refresh_user_health_score

        refresh_user_health_score(conn, user_id, today.month, today.year, invalidate_insights=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("financial_state recalc failed uid=%s: %s", user_id, exc)

  # Step 6 — score + existing fraud post-upload
    try:
        from services.fraud_pipeline import run_post_upload_pipeline

        summary["fraud_pipeline"] = run_post_upload_pipeline(
            user_id, conn, document_id=document_id
        )
    except Exception:
        logger.exception("score_transactions failed user_id=%s", user_id)
        summary["fraud_pipeline"] = {}

    # Step 7 — dark patterns
    try:
        summary["dark_patterns"] = _persist_dark_patterns(conn, user_id, scope)
    except Exception:
        logger.exception("detect_dark_patterns failed user_id=%s", user_id)
        summary["dark_patterns"] = {}

    # Step 8 — EMI
    try:
        summary["emi"] = _detect_emi_patterns(conn, user_id, scope)
    except Exception:
        logger.exception("detect_emi_patterns failed user_id=%s", user_id)
        summary["emi"] = {}

    # Step 9 — ML retrain when enough debits
    try:
        summary["ml_retrained"] = _retrain_ml_if_ready(user_id, conn)
    except Exception:
        summary["ml_retrained"] = False

    # Step 10 — health / monthly summaries
    try:
        _recalculate_health_score(conn, user_id, date_range)
        summary["health_synced"] = True
    except Exception:
        logger.exception("recalculate_health_score failed user_id=%s", user_id)
        summary["health_synced"] = False

    # Step 11 — client refresh signal
    emit_data_updated(user_id, source_name)
    summary["data_updated"] = True

    return summary


def run_post_import_background(
    user_id: int,
    *,
    source_name: str = "Statement",
    scope: str | None = "merged",
    date_range: dict | None = None,
    purge_orphans: bool = True,
    document_id: int | None = None,
) -> None:
    """Background worker — own DB connection (upload HTTP response already returned)."""
    from db import get_connection

    conn = get_connection()
    try:
        run_post_import_pipeline(
            user_id,
            conn,
            source_name=source_name,
            scope=scope,
            date_range=date_range,
            purge_orphans=purge_orphans,
            document_id=document_id,
            skip_heavy_ml=False,
        )
        conn.commit()
        logger.info("post_import_background done user_id=%s", user_id)
    except Exception:
        logger.exception("post_import_background failed user_id=%s", user_id)
        conn.rollback()
    finally:
        conn.close()
