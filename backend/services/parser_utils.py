"""Merchant normalization and category enrichment (global, all ingest paths)."""

from __future__ import annotations

import re

MERCHANT_CATEGORY_MAP: dict[str, str] = {
    "swiggy": "Food",
    "zomato": "Food",
    "eatsure": "Food",
    "blinkit": "Food",
    "zepto": "Food",
    "bigbasket": "Food",
    "amazon": "Shopping",
    "flipkart": "Shopping",
    "myntra": "Shopping",
    "meesho": "Shopping",
    "ajio": "Shopping",
    "uber": "Transport",
    "ola": "Transport",
    "rapido": "Transport",
    "netflix": "Entertainment",
    "spotify": "Entertainment",
    "hotstar": "Entertainment",
    "primevideo": "Entertainment",
    "byju": "Education",
    "unacademy": "Education",
    "coursera": "Education",
    "1mg": "Health",
    "pharmeasy": "Health",
    "apollo": "Health",
    "irctc": "Travel",
    "makemytrip": "Travel",
    "yatra": "Travel",
    "phonepe": "UPI Transfer",
    "googlepay": "UPI Transfer",
    "paytm": "UPI Transfer",
    "gpay": "UPI Transfer",
}

# Prompt labels → stored transaction.category vocabulary (categorizer.py)
ENRICH_TO_STORED: dict[str, str] = {
    "Food": "Food & Dining",
    "Shopping": "Shopping",
    "Transport": "Transportation",
    "Entertainment": "Entertainment",
    "Education": "Other",
    "Health": "Healthcare",
    "Travel": "Transportation",
    "UPI Transfer": "Transfer",
    "Others": "Others",
}


def normalize_merchant(merchant: str) -> str:
    m = (merchant or "").lower()
    m = re.sub(r"[^a-z0-9 ]", " ", m)
    m = re.sub(r"\d+", "", m).strip()
    return m.split()[0] if m.split() else "unknown"


def merchant_prefix_key(merchant: str) -> str:
    """Alphanumeric key for prefix map + DB normalized_merchant column."""
    m = (merchant or "").lower()
    m = re.sub(r"[^a-z0-9]", "", m)
    return (m[:100] if m else "unknown")


def enrich_category(merchant: str) -> str:
    key = merchant_prefix_key(merchant)
    if not key or key == "unknown":
        return "Others"
    for prefix, category in MERCHANT_CATEGORY_MAP.items():
        if key.startswith(prefix):
            return category
    return "Others"


def stored_category_for_merchant(merchant: str, raw_category: str | None = None) -> str:
    """Category written to transactions — enrich first, then legacy fallbacks.

    Must not call ``categorizer.resolve_category`` (that delegates here and caused
    RecursionError on every upload when LLM/parser supplied a raw category).
    """
    label = enrich_category(merchant)
    stored = ENRICH_TO_STORED.get(label, "Others")
    if stored != "Others":
        return stored
    if raw_category and str(raw_category).strip():
        from services.categorizer import normalize_category

        return normalize_category(raw_category)
    from services.categorizer import categorize_merchant, normalize_category

    return normalize_category(categorize_merchant(merchant))
