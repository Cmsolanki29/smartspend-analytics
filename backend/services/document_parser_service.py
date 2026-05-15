"""
Document Parser Service — extracts transactions from uploaded PDF / CSV / TXT files.

Uses OpenAI when OPENAI_API_KEY is set, otherwise Groq (same JSON extraction prompt).
pdfplumber is optional — if not installed, PDFs return a helpful message.
"""
from __future__ import annotations

import io
import json
from typing import Any

from services.ai_llm_provider import get_chat_client, get_chat_model, preferred_provider


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
