"""Upload amount sanity — balance column must not become transaction amount."""
from __future__ import annotations

from services.upload_amount_sanity import (
    amounts_look_like_running_balances,
    repair_running_balance_transactions,
    sanitize_transactions_before_import,
)


def _balance_only_rows() -> list[dict]:
    """Simulates PDF text parse storing closing balance as amount (Vijay-style)."""
    return [
        {"date": "2026-05-01", "description": "SALARY TCS", "amount": 407_359.0, "type": "credit"},
        {"date": "2026-05-02", "description": "QuickLoan", "amount": 395_359.0, "type": "debit"},
        {"date": "2026-05-02", "description": "Rent", "amount": 373_359.0, "type": "debit"},
        {"date": "2026-05-03", "description": "Electricity", "amount": 371_679.0, "type": "debit"},
        {"date": "2026-05-05", "description": "EMI Home", "amount": 350_446.0, "type": "debit"},
        {"date": "2026-05-10", "description": "SIP Axis", "amount": 326_630.0, "type": "debit"},
        {"date": "2026-05-11", "description": "Velocity UPI", "amount": 301_630.0, "type": "debit"},
        {"date": "2026-05-14", "description": "Spotify", "amount": 301_252.0, "type": "debit"},
    ]


def test_detects_running_balance_pattern():
    assert amounts_look_like_running_balances(_balance_only_rows()) is True


def test_repair_balance_rows_to_real_amounts():
    repaired = repair_running_balance_transactions(
        _balance_only_rows(),
        text="",
        monthly_income=85_000.0,
    )
    assert not amounts_look_like_running_balances(repaired)
    debits = sum(float(t["amount"]) for t in repaired if t["type"] == "debit")
    credits = sum(float(t["amount"]) for t in repaired if t["type"] == "credit")
    assert 80_000 <= credits <= 90_000
    assert 90_000 <= debits <= 120_000


def test_sanitize_repairs_when_balance_pattern_detected():
    rows = _balance_only_rows()
    out, meta = sanitize_transactions_before_import(rows, text="")
    assert meta.get("repaired_running_balance") is True
    assert len(out) >= 5
    assert not amounts_look_like_running_balances(out)
    assert all(float(t["amount"]) < 2_000_000 for t in out)
