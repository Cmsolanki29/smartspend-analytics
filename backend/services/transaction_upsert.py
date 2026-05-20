"""Shared transaction row enrichment before any DB insert/upsert."""

from __future__ import annotations

from typing import Any

from services.parser_utils import merchant_prefix_key, stored_category_for_merchant


def enrich_transaction_row(
    row: dict[str, Any],
    *,
    merchant_key: str = "merchant",
    category_key: str = "category",
) -> dict[str, Any]:
    """
    Mutates and returns ``row`` with ``category`` and ``normalized_merchant`` set.
    Call on every transaction dict before INSERT (PDF, CSV, bank link, AI merge).
    """
    merchant = (
        row.get(merchant_key)
        or row.get("description")
        or row.get("payee")
        or ""
    )
    merchant_s = str(merchant).strip()[:200] or "Unknown"
    row[merchant_key] = merchant_s
    try:
        row[category_key] = stored_category_for_merchant(
            merchant_s, row.get(category_key)
        )
    except Exception:  # noqa: BLE001 — never fail an entire upload on categorization
        row[category_key] = "Others"
    try:
        row["normalized_merchant"] = merchant_prefix_key(merchant_s)
    except Exception:  # noqa: BLE001
        row["normalized_merchant"] = "unknown"
    return row
