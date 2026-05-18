"""
Merge LLM-extracted document rows into the unified `transactions` ledger.

Used by AI chat document upload so bank statements / card bills / exports
become first-class data for dashboard, anomalies, and health — same as CSV import.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from services.transaction_upsert import enrich_transaction_row

# LLM document parser uses lowercase slugs; map into app category vocabulary.
_DOC_CATEGORY_MAP: dict[str, str] = {
    "food": "Food & Dining",
    "emi": "Finance & Investment",
    "salary": "Salary",
    "shopping": "Shopping",
    "utilities": "Bills & Utilities",
    "transfer": "Transfer",
    "entertainment": "Entertainment",
    "other": "Others",
}

_DOC_TYPE_TO_ORIGIN: dict[str, str] = {
    "bank_statement": "bank_statement",
    "credit_card_bill": "credit_card",
    "emi_schedule": "emi_schedule",
    "upi_history": "upi_export",
    "salary_slip": "salary_document",
    "other": "ai_document",
}


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val).strip()[:10]
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _parse_amount(val: Any) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val).replace(",", "").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _parse_txn_type(val: Any) -> str:
    s = str(val or "debit").strip().lower()
    if s in ("credit", "cr", "c"):
        return "CREDIT"
    return "DEBIT"


def _document_origin(extracted: dict[str, Any]) -> str:
    dt = (extracted.get("document_type") or "other").strip().lower()
    return _DOC_TYPE_TO_ORIGIN.get(dt, "ai_document")


def merge_extracted_into_ledger(
    conn,
    user_id: int,
    source_document_id: str,
    extracted: dict[str, Any],
) -> dict[str, int]:
    """
    Insert extracted ``transactions`` JSON into ``transactions``.

    Returns counts: inserted, skipped_duplicates, skipped_invalid.
    Caller is responsible for ``conn.commit()`` (or rollback).
    """
    cur = conn.cursor()
    document_origin = _document_origin(extracted)
    doc_type = (extracted.get("document_type") or "other").strip()[:50] or "other"
    rows = extracted.get("transactions") or []
    if not isinstance(rows, list):
        rows = []

    inserted = 0
    skipped_duplicates = 0
    skipped_invalid = 0

    try:
        cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
        if not cur.fetchone():
            return {"inserted": 0, "skipped_duplicates": 0, "skipped_invalid": 0}

        for raw in rows:
            if not isinstance(raw, dict):
                skipped_invalid += 1
                continue

            d = _parse_date(raw.get("date"))
            amt = _parse_amount(raw.get("amount"))
            if d is None or amt is None or amt <= 0:
                skipped_invalid += 1
                continue

            desc = (raw.get("description") or "").strip() or None
            enriched = enrich_transaction_row(
                {
                    "merchant": (desc or "Unknown")[:200],
                    "category": raw.get("category"),
                    "description": desc,
                }
            )
            merchant = enriched["merchant"]
            txn_type = _parse_txn_type(raw.get("type"))
            cat = str(enriched["category"])[:50]
            normalized_merchant = enriched["normalized_merchant"]

            cur.execute(
                """
                SELECT 1 FROM transactions
                WHERE user_id = %s
                  AND transaction_date = %s
                  AND type = %s
                  AND amount = %s
                  AND (
                        lower(trim(coalesce(description,''))) = lower(trim(%s))
                     OR lower(trim(coalesce(merchant,''))) = lower(trim(%s))
                  )
                LIMIT 1;
                """,
                (user_id, d, txn_type, amt, desc or "", merchant or ""),
            )
            if cur.fetchone():
                skipped_duplicates += 1
                continue

            tt = time(12, 0, 0)
            hod = 12
            dow = d.weekday()
            wknd = dow >= 5
            night = False

            cur.execute(
                """
                INSERT INTO transactions (
                    user_id, transaction_date, transaction_time, amount, type, description,
                    merchant, normalized_merchant, category, subcategory, payment_method, location,
                    anomaly_flag, risk_score, risk_level, anomaly_reason, ml_processed,
                    hour_of_day, day_of_week, is_weekend, is_night_txn,
                    document_origin, source_document_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    FALSE, 0, 'LOW', NULL, FALSE,
                    %s, %s, %s, %s,
                    %s, %s::uuid
                );
                """,
                (
                    user_id,
                    d,
                    tt,
                    float(amt),
                    txn_type,
                    desc,
                    merchant[:200],
                    normalized_merchant,
                    cat,
                    doc_type,
                    "DocumentImport",
                    None,
                    hod,
                    dow,
                    wknd,
                    night,
                    document_origin,
                    source_document_id,
                ),
            )
            inserted += 1
    finally:
        cur.close()

    return {
        "inserted": inserted,
        "skipped_duplicates": skipped_duplicates,
        "skipped_invalid": skipped_invalid,
    }
