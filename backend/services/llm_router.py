"""
Smart LLM Router — task-based routing across OpenAI, Groq, and Gemini.

Extraction pipeline only; chat/insights keep using ai_llm_provider.py.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from typing import Any

from services.ai_llm_provider import _env_val, _groq_key, _openai_key

logger = logging.getLogger(__name__)

_router: "LLMRouter | None" = None


def get_llm_router(*, required: bool = True) -> "LLMRouter | None":
    """Module-level singleton (initialized on first use)."""
    global _router
    if _router is not None:
        return _router
    try:
        _router = LLMRouter()
        return _router
    except RuntimeError:
        if required:
            raise
        return None


class LLMRouter:
    """Routes extraction tasks to the best available model with ordered fallback."""

    def __init__(self) -> None:
        self.providers: dict[str, dict[str, Any]] = {}
        self._call_log: list[dict[str, Any]] = []
        self._init_providers()
        if not self.providers:
            logger.critical("NO LLM PROVIDERS AVAILABLE. Check API keys:")
            logger.critical(f"  OPENAI_API_KEY: {'SET' if _openai_key() else 'MISSING'}")
            logger.critical(f"  GROQ_API_KEY: {'SET' if _groq_key() else 'MISSING'}")
            gemini_key = _env_val("GEMINI_API_KEY") or _env_val("GOOGLE_API_KEY")
            logger.critical(f"  GEMINI/GOOGLE_API_KEY: {'SET' if gemini_key else 'MISSING'}")
            raise RuntimeError(
                "No LLM providers configured. Set OPENAI_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY."
            )
        logger.info("LLM Router ready: %s", list(self.providers.keys()))

    def _init_providers(self) -> None:
        if _openai_key():
            try:
                from openai import OpenAI

                self.providers["openai"] = {
                    "client": OpenAI(api_key=_openai_key(), timeout=30.0),
                    "model": _env_val("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
                    "vision_model": _env_val("OPENAI_VISION_MODEL", "gpt-4o") or "gpt-4o",
                    "type": "openai",
                }
                logger.info("OpenAI provider ready (%s)", self.providers["openai"]["model"])
            except Exception as exc:
                logger.warning("OpenAI init failed: %s", exc)

        if _groq_key():
            try:
                from groq import Groq

                self.providers["groq"] = {
                    "client": Groq(api_key=_groq_key(), timeout=15.0),
                    "model": _env_val(
                        "GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
                    )
                    or "meta-llama/llama-4-scout-17b-16e-instruct",
                    "type": "groq",
                }
                logger.info("Groq provider ready (%s)", self.providers["groq"]["model"])
            except Exception as exc:
                logger.warning("Groq init failed: %s", exc)

        gemini_key = _env_val("GEMINI_API_KEY") or _env_val("GOOGLE_API_KEY")
        if gemini_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=gemini_key)
                self.providers["gemini"] = {
                    "client": genai,
                    "model_name": _env_val("GEMINI_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash",
                    "type": "gemini",
                }
                logger.info("Gemini provider ready (%s)", self.providers["gemini"]["model_name"])
            except Exception as exc:
                logger.warning("Gemini init failed: %s", exc)

    def usage_summary(self) -> str:
        """Compact audit string of models used this request."""
        if not self._call_log:
            return ""
        parts = []
        for entry in self._call_log:
            parts.append(f"{entry['provider']}:{entry['model']}({entry['task']})")
        return " | ".join(parts)

    def get_call_log(self) -> list[dict[str, Any]]:
        return list(self._call_log)

    # ── Task APIs ─────────────────────────────────────────────────────────────

    def extract_transactions_bulk(
        self,
        text_chunk: str,
        doc_info: dict[str, Any],
        chunk_index: int = 0,
        total_chunks: int = 1,
    ) -> list[dict[str, Any]]:
        institution = doc_info.get("institution_name", "financial institution")
        prompt = f"""Extract ALL transactions from this {institution} statement section (part {chunk_index + 1} of {total_chunks}).

RULES:
- Extract EVERY transaction. Missing even one is failure.
- Date: YYYY-MM-DD. Convert Indian formats (DD-MM-YYYY, DD/MM/YY, DD-MMM-YYYY).
- Amount: positive number only. No commas, no ₹, no INR.
- Type: "debit" or "credit".
- NO limit on count.

TEXT:
{text_chunk}

Return ONLY a JSON array:
[{{"date":"YYYY-MM-DD","description":"exact text","amount":1234.56,"type":"debit"}}]
If none: []"""

        raw = self._call_with_fallback(
            prompt=prompt,
            task_name="bulk_extraction",
            primary="groq",
            fallbacks=["openai", "gemini"],
            max_tokens=8000,
            temperature=0.0,
        )
        return self.sanitize_transactions(self._safe_parse_json_list(raw))

    def understand_document(self, text_sample: str) -> dict[str, Any]:
        prompt = f"""Analyze this financial document and extract metadata.
IMPORTANT: Extract institution_name ONLY from the document text itself.
Do NOT guess or infer the bank from any other context.
If you cannot find the bank name clearly in the text, return null.

DOCUMENT:
{text_sample[:5000]}

Return ONLY JSON:
{{
    "document_type": "bank_statement|credit_card_statement|loan_statement|transfer_receipt|unknown",
    "institution_name": "exact name from document text only, e.g. ICICI Bank, HDFC Bank, SBI — null if not found",
    "account_type": "savings|current|credit_card|loan|unknown",
    "account_number_masked": "last 4 digits only e.g. XXXX4812 or null",
    "account_holder_name": "full name exactly as printed in document or null",
    "statement_period": "date range as written in document or null",
    "currency": "INR",
    "opening_balance": null,
    "closing_balance": null,
    "total_debits": null,
    "total_credits": null,
    "total_due": null,
    "estimated_transaction_count": 0
}}

Extract ONLY what is explicitly written in the document. Return null for anything not clearly visible."""

        raw = self._call_with_fallback(
            prompt=prompt,
            task_name="document_understanding",
            primary="openai",
            fallbacks=["gemini", "groq"],
            max_tokens=2000,
            temperature=0.0,
        )
        result = self._safe_parse_json_dict(raw)
        for key in ("institution_name", "account_holder_name", "statement_period"):
            val = result.get(key)
            if isinstance(val, str) and val.strip().lower() in ("", "null", "none", "unknown", "n/a"):
                result[key] = None
        logger.info(
            "[document_understanding] institution_name=%r account_holder_name=%r document_type=%r",
            result.get("institution_name"),
            result.get("account_holder_name"),
            result.get("document_type"),
        )
        return result

    def validate_extraction(
        self,
        original_text: str,
        doc_info: dict[str, Any],
        transactions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        expected = doc_info.get("estimated_transaction_count", "unknown")
        total_due = doc_info.get("total_due") or doc_info.get("total_debits") or "unknown"
        actual_count = len(transactions)
        actual_sum = sum(
            float(t.get("amount", 0))
            for t in transactions
            if str(t.get("type", "debit")).lower() != "credit"
        )
        existing_summary = "\n".join(
            f"  {t.get('date', '?')} | {str(t.get('description', ''))[:35]} | {t.get('amount', 0)}"
            for t in transactions[:40]
        )
        prompt = f"""Verify transaction extraction completeness.

Expected count: ~{expected}
Document total debits/due: {total_due}
Extracted: {actual_count} transactions, debit sum {actual_sum}

EXTRACTED (first 40):
{existing_summary}

DOCUMENT TEXT:
{original_text[:5000]}

Return ONLY JSON:
{{
    "is_complete": true,
    "issues": [],
    "missed_transactions": [],
    "corrected_transactions": []
}}"""

        raw = self._call_with_fallback(
            prompt=prompt,
            task_name="validation",
            primary="openai",
            fallbacks=["gemini", "groq"],
            max_tokens=4000,
            temperature=0.0,
        )
        return self._safe_parse_json_dict(raw)

    def apply_validation_result(
        self,
        transactions: list[dict[str, Any]],
        validation: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Merge missed/corrected transactions from validation agent."""
        issues = list(validation.get("issues") or [])
        existing_keys = {
            f"{t.get('date')}|{t.get('amount', 0)}|{str(t.get('description', ''))[:20]}"
            for t in transactions
        }

        for txn in validation.get("missed_transactions") or []:
            if not isinstance(txn, dict):
                continue
            txn = self.sanitize_transactions([txn])
            if not txn:
                continue
            txn = txn[0]
            key = f"{txn.get('date')}|{txn.get('amount', 0)}|{str(txn.get('description', ''))[:20]}"
            if key not in existing_keys:
                transactions.append(txn)
                existing_keys.add(key)

        corrections = {c.get("original_description"): c for c in validation.get("corrected_transactions") or [] if isinstance(c, dict)}
        if corrections:
            for t in transactions:
                desc = t.get("description", "")
                if desc in corrections:
                    corr = corrections[desc]
                    if corr.get("corrected_amount") is not None:
                        try:
                            t["amount"] = float(corr["corrected_amount"])
                        except (TypeError, ValueError):
                            pass

        transactions.sort(key=lambda x: x.get("date", ""))
        return transactions, issues

    def categorize_transactions(self, transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not transactions:
            return transactions

        batch_size = 40
        categories_taxonomy = (
            "food_dining, groceries, shopping_online, shopping_offline, fuel_transport, "
            "entertainment, utilities, rent_housing, emi_loan, insurance, investment, "
            "salary_income, transfer, medical_health, education, travel, subscriptions, "
            "cash_withdrawal, government, other"
        )

        for i in range(0, len(transactions), batch_size):
            batch = transactions[i : i + batch_size]
            txn_list = "\n".join(
                f"{j + 1}. {t.get('description', '')} | ₹{t.get('amount', 0)} | {t.get('type', 'debit')}"
                for j, t in enumerate(batch)
            )
            prompt = f"""Categorize Indian financial transactions. ONE category each.

CATEGORIES: {categories_taxonomy}

TRANSACTIONS:
{txn_list}

Return ONLY JSON array of {len(batch)} category strings in order."""

            raw = self._call_with_fallback(
                prompt=prompt,
                task_name="categorization",
                primary="openai",
                fallbacks=["gemini", "groq"],
                max_tokens=2000,
                temperature=0.0,
            )
            categories = self._safe_parse_json_list(raw)
            for j, txn in enumerate(batch):
                txn["category"] = categories[j] if j < len(categories) else "other"
        return transactions

    def read_image_as_text(self, image_base64: str, mime_type: str = "image/png") -> str:
        prompt = (
            "Extract ALL text from this financial document image exactly as shown. "
            "Include every number, date, amount, and description. Preserve table structure."
        )

        if "gemini" in self.providers:
            try:
                genai = self.providers["gemini"]["client"]
                model = genai.GenerativeModel(self.providers["gemini"]["model_name"])
                image_bytes = base64.b64decode(image_base64)
                start = time.time()
                response = model.generate_content(
                    [prompt, {"mime_type": mime_type, "data": image_bytes}],
                    generation_config={"max_output_tokens": 8000, "temperature": 0},
                )
                text = (response.text or "").strip()
                elapsed = time.time() - start
                if len(text) > 50:
                    self._log_call("gemini", self.providers["gemini"]["model_name"], "vision_read", elapsed, len(text))
                    return text
            except Exception as exc:
                if self._is_rate_limit(exc):
                    logger.warning("Gemini vision rate limited: %s", exc)
                else:
                    logger.warning("Gemini vision failed: %s", exc)

        if "openai" in self.providers:
            try:
                client = self.providers["openai"]["client"]
                vision_model = self.providers["openai"]["vision_model"]
                start = time.time()
                response = client.chat.completions.create(
                    model=vision_model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}},
                        ],
                    }],
                    max_tokens=8000,
                    temperature=0.0,
                )
                text = (response.choices[0].message.content or "").strip()
                elapsed = time.time() - start
                if len(text) > 50:
                    self._log_call("openai", vision_model, "vision_read", elapsed, len(text))
                    return text
            except Exception as exc:
                if self._is_rate_limit(exc):
                    logger.warning("OpenAI vision rate limited: %s", exc)
                else:
                    logger.warning("OpenAI vision failed: %s", exc)

        return ""

    def verify_extraction_visually(
        self,
        image_base64: str,
        extracted_text: str,
        mime_type: str = "image/png",
    ) -> dict[str, Any]:
        prompt = f"""Compare this document image with extracted text.

EXTRACTED TEXT:
{extracted_text[:3000]}

Return ONLY JSON:
{{"match": true, "score": 15, "missing_sections": [], "issues": []}}
Score 0-15 for extraction quality."""

        if "gemini" in self.providers:
            try:
                genai = self.providers["gemini"]["client"]
                model = genai.GenerativeModel(self.providers["gemini"]["model_name"])
                image_bytes = base64.b64decode(image_base64)
                response = model.generate_content(
                    [prompt, {"mime_type": mime_type, "data": image_bytes}],
                    generation_config={"max_output_tokens": 2000, "temperature": 0},
                )
                result = self._safe_parse_json_dict(response.text or "")
                if result:
                    self._log_call("gemini", self.providers["gemini"]["model_name"], "visual_verify", 0, 0)
                    return result
            except Exception as exc:
                logger.warning("Gemini visual verify failed: %s", exc)

        if "openai" in self.providers:
            try:
                client = self.providers["openai"]["client"]
                vision_model = self.providers["openai"]["vision_model"]
                response = client.chat.completions.create(
                    model=vision_model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}},
                        ],
                    }],
                    max_tokens=2000,
                    temperature=0.0,
                )
                result = self._safe_parse_json_dict(response.choices[0].message.content or "")
                if result:
                    self._log_call("openai", vision_model, "visual_verify", 0, 0)
                    return result
            except Exception as exc:
                logger.warning("OpenAI visual verify failed: %s", exc)

        return {"match": False, "score": 0, "issues": ["All vision providers failed"]}

    # ── Core call machinery ───────────────────────────────────────────────────

    def _call_with_fallback(
        self,
        prompt: str,
        task_name: str,
        primary: str,
        fallbacks: list[str],
        max_tokens: int = 4000,
        temperature: float = 0.0,
    ) -> str:
        order = [primary] + [f for f in fallbacks if f != primary]
        for provider_name in order:
            if provider_name not in self.providers:
                continue
            try:
                start = time.time()
                result = self._call_provider(provider_name, prompt, max_tokens, temperature)
                elapsed = time.time() - start
                if result and len(result.strip()) > 2:
                    model = self._model_name(provider_name)
                    est_in = len(prompt.split()) * 1.3
                    est_out = len(result.split()) * 1.3
                    logger.info(
                        "[%s] %s | model=%s | ~%.0fin+~%.0fout | %.1fs",
                        task_name,
                        provider_name,
                        model,
                        est_in,
                        est_out,
                        elapsed,
                    )
                    self._log_call(provider_name, model, task_name, elapsed, len(result))
                    return result
                logger.warning("[%s] %s returned empty", task_name, provider_name)
            except Exception as exc:
                if self._is_rate_limit(exc):
                    logger.warning("[%s] %s rate limited — trying fallback", task_name, provider_name)
                else:
                    logger.warning("[%s] %s failed: %s", task_name, provider_name, exc)
        logger.error("[%s] ALL providers failed", task_name)
        return ""

    def _call_provider(
        self,
        provider_name: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        provider = self.providers[provider_name]
        if provider["type"] == "openai":
            response = provider["client"].chat.completions.create(
                model=provider["model"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return (response.choices[0].message.content or "").strip()

        if provider["type"] == "groq":
            response = provider["client"].chat.completions.create(
                model=provider["model"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return (response.choices[0].message.content or "").strip()

        if provider["type"] == "gemini":
            genai = provider["client"]
            model = genai.GenerativeModel(provider["model_name"])
            response = model.generate_content(
                prompt,
                generation_config={"max_output_tokens": max_tokens, "temperature": temperature},
            )
            return (response.text or "").strip()

        raise ValueError(f"Unknown provider type: {provider['type']}")

    def _model_name(self, provider_name: str) -> str:
        p = self.providers[provider_name]
        if p["type"] == "gemini":
            return p["model_name"]
        return p.get("model") or p.get("vision_model", provider_name)

    def _log_call(self, provider: str, model: str, task: str, elapsed: float, out_len: int) -> None:
        self._call_log.append({
            "provider": provider,
            "model": model,
            "task": task,
            "elapsed_s": round(elapsed, 2),
            "output_chars": out_len,
        })

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        name = type(exc).__name__
        if name in ("RateLimitError", "ResourceExhausted"):
            return True
        msg = str(exc).lower()
        return "rate" in msg or "429" in msg or "quota" in msg

    @staticmethod
    def sanitize_transactions(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        valid: list[dict[str, Any]] = []
        for txn in raw:
            if not isinstance(txn, dict):
                continue
            if not txn.get("date"):
                continue
            amount = txn.get("amount")
            try:
                if isinstance(amount, str):
                    amount = float(amount.replace(",", "").replace("₹", "").replace("INR", "").strip())
                amount = float(amount)
            except (TypeError, ValueError):
                continue
            if amount <= 0:
                continue
            txn["amount"] = amount
            raw_type = str(txn.get("type", "debit")).lower()
            txn["type"] = "credit" if raw_type in ("credit", "cr", "deposit") else "debit"
            valid.append(txn)
        return valid

    @staticmethod
    def _safe_parse_json_list(text: str) -> list[Any]:
        if not text:
            return []
        cleaned = text.strip()
        cleaned = re.sub(r"^```json\s*", "", cleaned)
        cleaned = re.sub(r"^```\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        try:
            result = json.loads(cleaned)
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", cleaned)
            if match:
                try:
                    result = json.loads(match.group())
                    return result if isinstance(result, list) else []
                except json.JSONDecodeError:
                    pass
        return []

    @staticmethod
    def _safe_parse_json_dict(text: str) -> dict[str, Any]:
        if not text:
            return {}
        cleaned = text.strip()
        cleaned = re.sub(r"^```json\s*", "", cleaned)
        cleaned = re.sub(r"^```\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        try:
            result = json.loads(cleaned)
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    result = json.loads(match.group())
                    return result if isinstance(result, dict) else {}
                except json.JSONDecodeError:
                    pass
        return {}
