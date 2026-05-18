"""Merchant familiarity trust — reduces false ML fraud flags for repeat merchants."""

from __future__ import annotations

from typing import Any

from services.parser_utils import merchant_prefix_key

TRUST_DEBIT_THRESHOLD = 5
TRUST_RISK_CAP = 30


def merchant_key_for_row(row: dict[str, Any]) -> str:
    raw = row.get("normalized_merchant") or row.get("merchant") or ""
    key = str(raw).strip()
    if key and key != "unknown":
        return key[:100]
    return merchant_prefix_key(str(row.get("merchant") or ""))


def fetch_merchant_debit_counts_90d(
    cursor,
    user_id: int,
    merchant_keys: list[str],
) -> dict[str, int]:
    keys = sorted({k for k in merchant_keys if k and k != "unknown"})
    if not keys:
        return {}
    cursor.execute(
        """
        SELECT normalized_merchant, COUNT(*)::int
        FROM transactions
        WHERE user_id = %s
          AND UPPER(COALESCE(type, '')) = 'DEBIT'
          AND COALESCE(amount, 0) > 0
          AND transaction_date >= CURRENT_DATE - INTERVAL '90 days'
          AND normalized_merchant = ANY(%s)
        GROUP BY normalized_merchant;
        """,
        (user_id, keys),
    )
    return {str(r[0]): int(r[1] or 0) for r in cursor.fetchall()}


def apply_merchant_trust_rule(
    risk_score: int,
    anomaly_flag: bool,
    *,
    count_90d: int,
) -> tuple[int, bool]:
    """Cap risk and clear anomaly when merchant is familiar (≥5 debits / 90d)."""
    if count_90d >= TRUST_DEBIT_THRESHOLD:
        return min(int(risk_score), TRUST_RISK_CAP), False
    return int(risk_score), bool(anomaly_flag)
