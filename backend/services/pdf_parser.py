"""
PDFParserAgent — wraps document_parser_service and integrates with
connected_sources + uploaded_documents for structured import.
Uses OpenAI (or Groq fallback) via ai_llm_provider.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from services.document_parser_service import extract_text_from_bytes, classify_and_extract

_CREDIT_KEYWORDS = {"credit", "cr", "deposit", "salary", "refund", "cashback", "received", "reversal"}
_TRANSFER_KEYWORDS = {
    "credit card payment", "cc payment", "card payment", "payment received",
    "payment towards", "autopay", "inward transfer", "outward transfer",
}


def _normalise_type(raw: str | None) -> str:
    r = (raw or "").lower().strip()
    if any(k in r for k in _CREDIT_KEYWORDS):
        return "CREDIT"
    return "DEBIT"


def _is_internal_transfer(merchant: str, description: str) -> bool:
    combined = f"{merchant} {description}".lower()
    return any(k in combined for k in _TRANSFER_KEYWORDS)


class PDFParserAgent:
    """Extract, validate, deduplicate and insert transactions from uploaded files."""

    def extract_transactions(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: int,
        document_id: int,
        connected_source_id: int | None,
        conn,                           # psycopg2 connection (from get_db)
    ) -> dict[str, Any]:
        """Full pipeline: parse → validate → deduplicate → insert."""

        self._set_status(conn, document_id, "processing")
        conn.commit()

        text = extract_text_from_bytes(file_bytes, filename)
        if text.startswith("["):
            self._mark_failed(conn, document_id, text)
            conn.commit()
            return {"success": False, "error": text}

        parsed = classify_and_extract(text)
        transactions = parsed.get("transactions", [])

        imported = duplicates = invalid = internal = 0

        for txn in transactions:
            if not self._is_valid(txn):
                invalid += 1
                continue

            merchant = (txn.get("description") or "").strip()[:100] or "Unknown"
            desc = (txn.get("description") or "")[:200]
            try:
                amount = float(txn.get("amount", 0))
            except (TypeError, ValueError):
                invalid += 1
                continue
            if amount <= 0:
                invalid += 1
                continue

            raw_type = _normalise_type(txn.get("type"))
            txn_date = self._parse_date(txn.get("date", ""))
            if not txn_date:
                invalid += 1
                continue

            if _is_internal_transfer(merchant, desc):
                internal += 1
                continue

            if self._is_duplicate(conn, user_id, txn_date, merchant, amount):
                duplicates += 1
                continue

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO transactions
                      (user_id, amount, type, category, merchant,
                       transaction_date, description,
                       uploaded_document_id, connected_source_id, data_origin)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pdf_upload')
                    """,
                    (
                        user_id,
                        amount,
                        raw_type,
                        txn.get("category", "other"),
                        merchant,
                        txn_date,
                        desc,
                        document_id,
                        connected_source_id,
                    ),
                )
            imported += 1

        self._mark_completed(conn, document_id, len(transactions), imported, duplicates)
        conn.commit()

        return {
            "success": True,
            "institution": parsed.get("institution", "unknown"),
            "document_type": parsed.get("document_type", "other"),
            "date_range": parsed.get("date_range"),
            "extracted": len(transactions),
            "imported": imported,
            "duplicates": duplicates,
            "internal_transfers_skipped": internal,
            "invalid": invalid,
        }

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _parse_date(raw: str) -> str | None:
        raw = (raw or "").strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%b %d, %Y", "%b %d %Y"):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
        return m.group(1) if m else None

    @staticmethod
    def _is_valid(txn: dict) -> bool:
        try:
            return bool(txn.get("date") and txn.get("description") and float(txn.get("amount", 0)) > 0)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _is_duplicate(conn, user_id: int, date: str, merchant: str, amount: float) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM transactions
                WHERE user_id = %s
                  AND transaction_date::date = %s
                  AND LOWER(merchant) = LOWER(%s)
                  AND ABS(amount - %s) < 5
                """,
                (user_id, date, merchant, amount),
            )
            return (cur.fetchone()[0] or 0) > 0

    @staticmethod
    def _set_status(conn, document_id: int, status: str) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE uploaded_documents SET extraction_status = %s WHERE id = %s",
                (status, document_id),
            )

    @staticmethod
    def _mark_completed(conn, document_id: int, extracted: int, imported: int, duplicates: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE uploaded_documents
                SET extraction_status = 'completed',
                    rows_extracted = %s, rows_imported = %s,
                    rows_skipped_duplicates = %s, processed_at = NOW()
                WHERE id = %s
                """,
                (extracted, imported, duplicates, document_id),
            )

    @staticmethod
    def _mark_failed(conn, document_id: int, error: str) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE uploaded_documents
                SET extraction_status = 'failed',
                    metadata = jsonb_build_object('error', %s),
                    processed_at = NOW()
                WHERE id = %s
                """,
                (error[:400], document_id),
            )
