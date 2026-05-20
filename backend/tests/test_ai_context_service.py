"""Unit tests for AI chat context grounding (no live DB)."""

from __future__ import annotations

from unittest.mock import patch

from services.ai_context_service import (
    _names_likely_match,
    _recurring_services_from_transactions,
    _summary_from_transactions,
    build_context_prompt_rules,
    merge_session_upload_into_packet,
)


def test_names_likely_match_chirag_variants():
    assert _names_likely_match("chirag solanki", "Chirag Solanki")
    assert _names_likely_match("CHIRAG SOLANKI", "chirag solanki")
    assert not _names_likely_match("chirag solanki", "Priya Mehta")


def test_summary_from_axis_like_transactions():
    txns = [
        {"amount": 649, "type": "DEBIT", "category": "Entertainment", "merchant": "Netflix"},
        {"amount": 4999, "type": "DEBIT", "category": "Shopping", "merchant": "Meta Ads"},
        {"amount": 1, "type": "DEBIT", "category": "Shopping", "merchant": "Apple.com"},
    ]
    summary = _summary_from_transactions(
        txns,
        period_label="Apr–May 2026",
        period_key="test",
        source="test",
    )
    assert summary["expense"] == 5649
    assert "Entertainment" in summary["categories"]
    assert "Spotify" not in str(summary["categories"])


def test_recurring_services_only_from_statement():
    txns = [
        {"amount": 649, "type": "DEBIT", "merchant": "Netflix India", "date": "2026-05-10"},
        {"amount": 312, "type": "DEBIT", "merchant": "Uber", "date": "2026-05-11"},
    ]
    subs = _recurring_services_from_transactions(txns)
    assert len(subs) == 1
    assert "netflix" in subs[0]["service"].lower()


def test_merge_session_upload_replaces_demo_subscriptions():
    packet = {
        "subscriptions": [{"service": "Spotify India", "amount": 299}],
        "recent_transactions": [{"merchant": "Rent", "amount": 28000, "type": "DEBIT"}],
        "monthly_summary": {"income": 75000, "expense": 67252},
    }
    ctx = {
        "doc_info": {"account_holder_name": "chirag solanki", "institution_name": "Axis Bank"},
        "identity_scope": {"scope": "unlinked_foreign", "reason": "different_person"},
        "transactions": [
            {
                "description": "Netflix",
                "amount": 649,
                "type": "debit",
                "category": "Entertainment",
                "date": "2026-05-01",
            },
        ],
        "health_preview": {
            "total_debits": 649,
            "total_credits": 0,
            "net": -649,
            "savings_rate_pct": 0,
        },
    }
    with patch("services.ai_context_service.load_upload_scope_context", return_value=ctx):
        out = merge_session_upload_into_packet(packet, "sess-fake")
    assert out["monthly_summary"]["expense"] == 649
    assert all("spotify" not in (s.get("service") or "").lower() for s in out.get("subscriptions") or [])


def test_build_context_prompt_rules_no_data():
    rules = build_context_prompt_rules({"user": {"name": "Test User"}, "has_data": False})
    assert "Test User" in rules
    assert "no scoped ledger" in rules.lower() or "no ledger" in rules.lower()
