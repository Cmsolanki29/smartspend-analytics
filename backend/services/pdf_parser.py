"""
PDFParserAgent — monster extraction pipeline for uploaded statements.

Stages: extract_with_retry → classify_and_extract_monster → validate → dedupe → insert.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
from datetime import datetime
from typing import Any

from services.ai_llm_provider import preferred_provider
from services.document_parser_service import classify_and_extract_monster
from services.transaction_upsert import enrich_transaction_row
from services.monster_extraction import extract_with_retry, update_extraction_llm_result
from services.statement_line_parser import best_deterministic_transactions
from services.transaction_enrichment import heuristic_anomaly

logger = logging.getLogger(__name__)

_CREDIT_KEYWORDS = {"credit", "cr", "deposit", "salary", "refund", "cashback", "received", "reversal"}
_CREDIT_NARRATION_HINTS = (
    "neft cr",
    "imps cr",
    "rtgs cr",
    "upi from",
    "upi cr",
    "salary",
    "payroll",
    "reimbursement",
    "interest credit",
    "int.pd",
    "interest paid",
    "credit interest",
)
_TRANSFER_KEYWORDS = (
    "credit card payment",
    "cc payment",
    "cc bill payment",
    "card bill payment",
    "payment towards credit card",
    "payment towards card",
    "payment towards cc",
    "payment to card",
    "cc autopay",
    "card autopay",
    "autopay cc",
    "autopay card",
    "imps self",
    "neft self",
    "transfer to self",
    "fund transfer self",
    "self transfer",
)


def _normalise_type(raw: str | None, description: str = "") -> str:
    r = (raw or "").lower().strip()
    combined = f"{r} {description}".lower()
    if any(k in combined for k in _CREDIT_NARRATION_HINTS):
        return "CREDIT"
    if any(k in r for k in _CREDIT_KEYWORDS):
        return "CREDIT"
    return "DEBIT"


def _is_internal_transfer(merchant: str, description: str) -> bool:
    combined = f"{merchant} {description}".lower()
    return any(k in combined for k in _TRANSFER_KEYWORDS)


def _agentic_first_enabled() -> bool:
    return os.getenv("SMARTSPEND_AGENTIC_FIRST", "1").lower() in ("1", "true", "yes")


def _try_agentic_extract(
    text: str,
    filename: str,
    tables: list | None,
) -> dict[str, Any]:
    """Run Groq/Gemini agentic router with a hard timeout, then caller may fallback."""
    timeout_s = float(os.getenv("SMARTSPEND_AGENTIC_TIMEOUT_SEC", "45") or "45")
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(
            classify_and_extract_monster,
            text,
            filename,
            tables,
            agentic_first=True,
        )
        try:
            return fut.result(timeout=max(5.0, timeout_s))
        except concurrent.futures.TimeoutError:
            logger.warning("Agentic LLM extract timed out after %ss", timeout_s)
            return {
                "institution": "",
                "document_type": "bank_statement",
                "date_range": None,
                "transactions": [],
                "total_extracted": 0,
                "method": "agentic_timeout",
                "llm_model": None,
                "validation_issues": [f"Agentic extract timed out after {timeout_s}s"],
            }


class PDFParserAgent:
    """Extract, validate, deduplicate and insert transactions from uploaded files."""

    def extract_transactions(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: int,
        document_id: int,
        connected_source_id: int | None,
        conn,
        *,
        skip_duplicate_check: bool | None = None,
    ) -> dict[str, Any]:
        self._set_status(conn, document_id, "processing")
        conn.commit()

        extraction = extract_with_retry(
            content=file_bytes,
            filename=filename,
            user_id=user_id,
            doc_id=document_id,
            conn=conn,
        )

        quality_score = extraction.get("quality_score", 0)
        text = (extraction.get("text") or "").strip()

        if quality_score < 30 and not text:
            err = extraction.get("error", "Could not extract text from document")
            self._mark_failed(conn, document_id, err)
            conn.commit()
            update_extraction_llm_result(
                conn,
                document_id,
                user_id,
                llm_raw="",
                model="",
                extracted=0,
                after_validation=0,
                validation_issues=[err],
                stored=0,
                categorization_method="none",
                status="failed",
                error=err,
            )
            return {"success": False, "error": err, "quality_score": quality_score}

        if text.startswith("[") and "error" in text.lower():
            self._mark_failed(conn, document_id, text)
            conn.commit()
            return {"success": False, "error": text, "quality_score": quality_score}

        deterministic, det_method = best_deterministic_transactions(
            text, extraction.get("tables")
        )
        min_det = 8
        tables = extraction.get("tables")
        use_agentic = _agentic_first_enabled() and preferred_provider() != "none"

        if use_agentic:
            logger.info("Upload: trying agentic LLM first (provider=%s)", preferred_provider())
            parsed = _try_agentic_extract(text, filename, tables)
            transactions = list(parsed.get("transactions") or [])
            if len(transactions) < min_det and len(deterministic) >= min_det:
                logger.info(
                    "Agentic returned %s rows; monster fallback %s (%s rows)",
                    len(transactions),
                    det_method,
                    len(deterministic),
                )
                transactions = deterministic
                parsed = {
                    "transactions": transactions,
                    "method": f"chunked_llm→{det_method}",
                    "institution": parsed.get("institution") or "",
                    "document_type": parsed.get("document_type") or "bank_statement",
                    "date_range": parsed.get("date_range"),
                    "validation_issues": list(parsed.get("validation_issues") or []),
                }
            elif deterministic and len(deterministic) > len(transactions):
                seen = {
                    f"{t.get('date','')}|{float(t.get('amount',0)):.2f}|{str(t.get('description',''))[:24].lower()}"
                    for t in transactions
                }
                for t in deterministic:
                    key = f"{t.get('date','')}|{float(t.get('amount',0)):.2f}|{str(t.get('description',''))[:24].lower()}"
                    if key not in seen:
                        transactions.append(t)
                        seen.add(key)
                parsed["transactions"] = transactions
                parsed["method"] = (parsed.get("method") or "chunked_llm") + f"+{det_method}"
        elif len(deterministic) >= min_det:
            transactions = deterministic
            parsed = {
                "transactions": transactions,
                "method": det_method,
                "institution": "",
                "document_type": "bank_statement",
                "date_range": None,
                "validation_issues": [],
            }
        else:
            parsed = classify_and_extract_monster(
                text=text,
                filename=filename,
                tables=tables,
                agentic_first=False,
            )
            transactions = parsed.get("transactions", [])
            if len(deterministic) >= len(transactions):
                transactions = deterministic
                parsed["method"] = det_method
            elif deterministic:
                seen = {
                    f"{t.get('date','')}|{float(t.get('amount',0)):.2f}|{str(t.get('description',''))[:24].lower()}"
                    for t in transactions
                }
                for t in deterministic:
                    key = f"{t.get('date','')}|{float(t.get('amount',0)):.2f}|{str(t.get('description',''))[:24].lower()}"
                    if key not in seen:
                        transactions.append(t)
                        seen.add(key)
                parsed["method"] = (parsed.get("method") or "chunked_llm") + f"+{det_method}"

        period = re.search(
            r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*-\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
            text,
            re.I,
        )
        if period and parsed.get("date_range") is None:
            parsed["date_range"] = f"{period.group(1)} - {period.group(2)}"
        period2 = re.search(
            r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\s*to\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
            text,
            re.I,
        )
        if period2 and parsed.get("date_range") is None:
            parsed["date_range"] = f"{period2.group(1)} - {period2.group(2)}"
        validation_issues: list[str] = list(extraction.get("quality_issues") or [])
        if parsed.get("validation_issues"):
            validation_issues.extend(parsed["validation_issues"])

        imported = duplicates = invalid = internal = 0
        if skip_duplicate_check is None:
            skip_duplicate_check = os.getenv("SMARTSPEND_SKIP_UPLOAD_DEDUP", "1").lower() in (
                "1",
                "true",
                "yes",
            )

        for txn in transactions:
            if not self._is_valid(txn):
                invalid += 1
                continue

            try:
                row = enrich_transaction_row(
                    {
                        "merchant": (txn.get("description") or "").strip()[:100] or "Unknown",
                        "category": txn.get("category"),
                        "description": (txn.get("description") or "")[:200],
                    }
                )
            except Exception as enrich_exc:  # noqa: BLE001
                logger.warning("Row enrich skipped: %s", enrich_exc)
                invalid += 1
                continue
            merchant = row["merchant"]
            desc = (row.get("description") or "")[:200]
            try:
                amount = float(txn.get("amount", 0))
            except (TypeError, ValueError):
                invalid += 1
                continue
            if amount <= 0:
                invalid += 1
                continue

            raw_type = _normalise_type(txn.get("type"), desc)
            txn_date = self._parse_date(txn.get("date", ""))
            if not txn_date:
                invalid += 1
                continue

            if _is_internal_transfer(merchant, desc):
                internal += 1
                continue

            if not skip_duplicate_check and self._is_duplicate(
                conn, user_id, txn_date, merchant, amount, connected_source_id
            ):
                duplicates += 1
                continue

            category = row["category"]
            normalized_merchant = row["normalized_merchant"]
            anomaly_flag, risk_score, risk_level, anomaly_reason = heuristic_anomaly(
                merchant, desc, amount, raw_type
            )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO transactions
                      (user_id, amount, type, category, merchant, normalized_merchant,
                       transaction_date, description,
                       uploaded_document_id, connected_source_id, data_origin,
                       anomaly_flag, risk_score, risk_level, anomaly_reason, ml_processed)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'monster_upload',
                            %s, %s, %s, %s, TRUE)
                    """,
                    (
                        user_id,
                        amount,
                        raw_type,
                        category,
                        merchant,
                        normalized_merchant,
                        txn_date,
                        desc,
                        document_id,
                        connected_source_id,
                        anomaly_flag,
                        risk_score,
                        risk_level,
                        anomaly_reason,
                    ),
                )
            imported += 1

        self._mark_completed(conn, document_id, len(transactions), imported, duplicates)
        conn.commit()

        if imported > 0:
            try:
                from services.transaction_enrichment import sync_all_monthly_summaries_for_user

                sync_all_monthly_summaries_for_user(conn, user_id)
                conn.commit()
            except Exception:  # noqa: BLE001
                logger.warning("monthly summary sync after import failed", exc_info=True)

        llm_raw = json.dumps({
            "institution": parsed.get("institution"),
            "document_type": parsed.get("document_type"),
            "transaction_count": len(transactions),
            "doc_info": parsed.get("doc_info"),
        })
        update_extraction_llm_result(
            conn,
            document_id,
            user_id,
            llm_raw=llm_raw,
            model=str(parsed.get("llm_model") or parsed.get("method") or "router")[:48],
            extracted=len(transactions),
            after_validation=len(transactions) - invalid,
            validation_issues=validation_issues,
            stored=imported,
            categorization_method=str(parsed.get("method", "chunked_llm"))[:48],
            status="completed",
        )

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
            "quality_score": quality_score,
            "extraction_method": extraction.get("method", "unknown"),
            "attempts": extraction.get("attempt_number", 1),
            "transactions_extracted": len(transactions),
            "transactions_stored": imported,
        }

    @staticmethod
    def _parse_date(raw: str) -> str | None:
        raw = (raw or "").strip()
        for fmt in (
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%d %b %Y",
            "%d-%b-%Y",
            "%d-%b-%y",
            "%b %d, %Y",
            "%b %d %Y",
        ):
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
    def _is_duplicate(
        conn,
        user_id: int,
        date: str,
        merchant: str,
        amount: float,
        connected_source_id: int | None,
    ) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM transactions t
                WHERE t.user_id = %s
                  AND t.transaction_date::date = %s
                  AND LOWER(t.merchant) = LOWER(%s)
                  AND ABS(t.amount - %s) < 5
                  AND t.connected_source_id IS NOT DISTINCT FROM %s
                """,
                (user_id, date, merchant, amount, connected_source_id),
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
