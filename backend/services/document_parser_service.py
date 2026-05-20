"""
Document Parser Service — extracts transactions from uploaded PDF / CSV / TXT / Excel / images.

Monster pipeline: chunked LLM extraction (no transaction cap), validation, categorization.
Legacy ``extract_text_from_bytes`` / ``classify_and_extract`` kept for compatibility.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
from typing import Any

from services.ai_llm_provider import get_chat_client, get_chat_model, preferred_provider
from services.llm_router import get_llm_router
from services.statement_line_parser import best_deterministic_transactions

logger = logging.getLogger(__name__)


def _pdfplumber():
    """Import at use-time so installs apply without restarting all workers."""
    import pdfplumber

    return pdfplumber


def extract_text_from_bytes(content: bytes, filename: str) -> str:
    """Extract raw text from PDF, CSV, or TXT bytes."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        try:
            pdfplumber = _pdfplumber()
        except Exception as exc:
            return f"[PDF: {filename} — could not load pdfplumber ({type(exc).__name__}: {exc}). pip install pdfplumber]"
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
            return "\n".join(pages_text)[:8000]
        except Exception as e:
            return f"[PDF parse error: {e}]"

    if ext == "csv":
        try:
            return content.decode("utf-8", errors="replace")[:8000]
        except Exception as e:
            return f"[CSV decode error: {e}]"

    if ext in ("txt", "text"):
        try:
            return content.decode("utf-8", errors="replace")[:8000]
        except Exception as e:
            return f"[TXT decode error: {e}]"

    return f"[Unsupported file type: .{ext}]"


def classify_and_extract(text: str) -> dict[str, Any]:
    """
    Classify the document and extract up to 30 structured transactions (single LLM call).

    Returns a dict matching the extracted_json schema stored in document_uploads.
    """
    if preferred_provider() == "none":
        return {
            "institution": "unknown",
            "document_type": "other",
            "date_range": None,
            "account_number_masked": None,
            "summary": "AI unavailable — set OPENAI_API_KEY or GROQ_API_KEY",
            "transactions": [],
        }

    # Use a 90s timeout — document extraction can be slow with gpt-4o-mini on busy keys.
    # Prefer Groq (fast, free tier) as first attempt; fall back to OpenAI on failure.
    client = get_chat_client(timeout=90.0)
    model = get_chat_model()

    # If Groq key is available and we're on OpenAI, swap to Groq for speed.
    if preferred_provider() == "openai":
        from services.ai_llm_provider import _env_val as _ev, _groq_key as _gk
        _gk_val = _gk()
        if _gk_val:
            from openai import OpenAI as _OAI
            client = _OAI(api_key=_gk_val, base_url="https://api.groq.com/openai/v1", timeout=60.0)
            model = _ev("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile") or "llama-3.3-70b-versatile"

    prompt = f"""You are a financial document classifier for Indian banks.

Analyze this document text and respond with ONLY valid JSON (no markdown fences, no preamble):

{{
  "institution": "bank or institution name (SBI | ICICI | HDFC | Axis Bank | Kotak | Yes Bank | Paytm | PhonePe | Google Pay | unknown)",
  "document_type": "one of: bank_statement | credit_card_bill | emi_schedule | upi_history | salary_slip | other",
  "date_range": "e.g. May 2026 or Apr–May 2026 or null",
  "account_number_masked": "last 4 digits if visible else null",
  "summary": "one sentence describing this document",
  "transactions": [
    {{
      "date": "YYYY-MM-DD",
      "description": "merchant or description",
      "amount": 1234.56,
      "type": "debit or credit",
      "category": "food | emi | salary | shopping | utilities | transfer | entertainment | other"
    }}
  ]
}}

Rules:
- Extract maximum 30 transactions. Use positive numbers for amounts.
- If the document is not in English, still extract amounts and dates.
- Dates that look like DD/MM/YYYY should be converted to YYYY-MM-DD.

Document text (first 4000 chars):
{text[:4000]}"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # Strip markdown fences if the model added them
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "institution": "unknown",
            "document_type": "other",
            "date_range": None,
            "account_number_masked": None,
            "summary": "Document parsed but structure could not be extracted",
            "transactions": [],
        }
    except Exception as e:
        print(f"[document_parser] LLM error: {e}")
        return {
            "institution": "unknown",
            "document_type": "other",
            "date_range": None,
            "account_number_masked": None,
            "summary": f"Parse failed: {str(e)[:100]}",
            "transactions": [],
        }


# ── Monster LLM pipeline (chunked, no 30-txn cap) ─────────────────────────────


def _safe_parse_json(raw: str) -> Any:
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\[[\s\S]*\]", cleaned)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


def _normalize_deterministic_transactions(tables: list) -> list[dict[str, Any]]:
    if not tables:
        return []
    first = tables[0]
    if not isinstance(first, list) or not first:
        return []
    out: list[dict[str, Any]] = []
    for row in first:
        if not isinstance(row, dict):
            continue
        if row.get("date") and row.get("amount"):
            out.append(row)
            continue
        if row.get("transaction_date") and row.get("amount"):
            d = row["transaction_date"]
            date_str = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
            out.append({
                "date": date_str,
                "description": row.get("description") or row.get("merchant") or "Unknown",
                "amount": float(row["amount"]),
                "type": "credit" if str(row.get("type", "")).upper() == "CREDIT" else "debit",
                "category": row.get("category", "other"),
            })
    return out


def _agentic_first_enabled() -> bool:
    return os.getenv("SMARTSPEND_AGENTIC_FIRST", "1").lower() in ("1", "true", "yes")


def _run_agentic_llm_pipeline(
    router: Any,
    text: str,
) -> dict[str, Any]:
    """Groq/Gemini agentic path: understand → chunked extract → validate → categorize."""
    doc_info = router.understand_document(text[:8000])
    transactions = _extract_with_router(router, text, doc_info)

    validation = router.validate_extraction(text, doc_info, transactions)
    validation_issues: list[str] = []
    if not validation.get("is_complete", True):
        transactions, validation_issues = router.apply_validation_result(transactions, validation)

    transactions = router.categorize_transactions(transactions)

    return {
        "institution": doc_info.get("institution_name", "unknown"),
        "document_type": doc_info.get("document_type", "other"),
        "date_range": doc_info.get("statement_period"),
        "transactions": transactions,
        "total_extracted": len(transactions),
        "method": "chunked_llm",
        "llm_model": router.usage_summary(),
        "doc_info": doc_info,
        "validation_issues": validation_issues,
    }


def _fallback_deterministic_extract(
    text: str,
    tables: list | None,
) -> dict[str, Any]:
    """Monster-style fallback — pdfplumber text + line parser, no LLM."""
    det_rows, det_method = best_deterministic_transactions(text, tables)
    if det_rows:
        return {
            "institution": "",
            "document_type": "bank_statement",
            "date_range": None,
            "transactions": det_rows,
            "total_extracted": len(det_rows),
            "method": det_method,
            "llm_model": None,
            "validation_issues": [],
        }
    return {
        "institution": "unknown",
        "document_type": "other",
        "date_range": None,
        "transactions": [],
        "total_extracted": 0,
        "method": "none",
        "llm_model": None,
        "validation_issues": [],
    }


def classify_and_extract_monster(
    text: str,
    filename: str = "",
    tables: list | None = None,
    *,
    agentic_first: bool | None = None,
) -> dict[str, Any]:
    """
    Transaction extraction.

    Default (``SMARTSPEND_AGENTIC_FIRST=1``): agentic LLM first, then deterministic fallback.
    When ``agentic_first=False``: legacy speed path (deterministic tables → LLM if needed).
    """
    use_agentic = _agentic_first_enabled() if agentic_first is None else bool(agentic_first)

    if not use_agentic:
        deterministic = _normalize_deterministic_transactions(tables or [])
        if deterministic:
            categorized = _categorize_transactions_llm(deterministic)
            return {
                "institution": "",
                "document_type": "bank_statement",
                "date_range": None,
                "transactions": categorized,
                "total_extracted": len(categorized),
                "method": "deterministic",
                "llm_model": None,
                "validation_issues": [],
            }

    router = get_llm_router(required=False)
    if router is not None:
        try:
            return _run_agentic_llm_pipeline(router, text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Agentic LLM pipeline failed (%s); using deterministic fallback", exc)

    return _fallback_deterministic_extract(text, tables)


def _extract_with_router(
    router: Any,
    text: str,
    doc_info: dict[str, Any],
) -> list[dict[str, Any]]:
    """Single-chunk or multi-chunk extraction via Groq-primary router."""
    if len(text) <= 5000:
        return router.extract_transactions_bulk(text, doc_info, 0, 1)

    chunk_size = 4000
    overlap = 500
    chunks: list[str] = []
    start = 0
    max_chunks = max(1, (len(text) // max(1, chunk_size - overlap)) + 2)
    iterations = 0
    while start < len(text) and iterations < max_chunks:
        iterations += 1
        end = min(start + chunk_size, len(text))
        if end < len(text):
            newline = text.rfind("\n", start + chunk_size - overlap, end)
            if newline > start:
                end = newline
        if end <= start:
            end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        next_start = end - overlap if end < len(text) else end
        if next_start <= start:
            next_start = end
        start = next_start

    all_transactions: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for i, chunk in enumerate(chunks):
        chunk_txns = router.extract_transactions_bulk(chunk, doc_info, i, len(chunks))
        for txn in chunk_txns:
            key = f"{txn['date']}|{txn.get('amount', 0)}|{str(txn.get('description', ''))[:20]}"
            if key not in seen_keys:
                seen_keys.add(key)
                all_transactions.append(txn)

    all_transactions.sort(key=lambda x: x.get("date", ""))
    return all_transactions


def _categorize_transactions_llm(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Legacy helper — delegates to LLM router."""
    router = get_llm_router(required=False)
    if router is None:
        return transactions
    return router.categorize_transactions(transactions)
