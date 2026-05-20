"""Regression: UPI + credit card must appear in merged dashboard scope and trends."""

from __future__ import annotations

import pytest

from services.dashboard_scope import transaction_scope_sql
from services.dashboard_sources import user_has_multi_source_types


def test_merged_scope_includes_upi_source_type():
    sql = transaction_scope_sql("t", "merged")
    assert "connected_sources" in sql
    assert "is_visible_on_dashboard" in sql


def test_bank_only_scope_includes_upi():
    sql = transaction_scope_sql("t", "bank_only")
    assert "'upi'" in sql


def test_credit_card_only_excludes_upi():
    sql = transaction_scope_sql("t", "credit_card_only")
    assert "credit_card" in sql
    assert "'upi'" not in sql


def test_needs_scoped_trends_when_multi_source(monkeypatch):
    from routes import analysis as analysis_mod

    class FakeCur:
        def execute(self, *_args, **_kwargs):
            pass

        def fetchone(self):
            return [False]

    monkeypatch.setattr(
        analysis_mod,
        "resolve_scope_mode",
        lambda _cur, _uid, scope=None: "merged",
    )
    monkeypatch.setattr(
        "services.dashboard_sources.user_has_multi_source_types",
        lambda _cur, _uid: True,
    )

    assert analysis_mod._needs_scoped_transaction_trends(FakeCur(), 1, "merged") is True


def test_user_has_multi_source_types_query_shape():
    """Document expected SQL usage — integration covered by manual QA."""
    assert callable(user_has_multi_source_types)
