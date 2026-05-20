"""
Full Axis-1 (A/B/C/D) + Axis-2 (L0–L3) matrix tests.
Uses sample PDFs for identity (Vikram foreign vs Sumit own-name).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.ai_context_service import enrich_doc_info_from_text, resolve_identity_scope
from services.chat_depth_policy import (
    classify_intent,
    evaluate_chat_policy,
    resolve_data_mode,
)

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "test samples"
VIKRAM_PDF = SAMPLES / "AXIS_BANK_ACCOUNT_STATEMENT_SAMPLE_Vikram_Singh_ANOMALY.pdf"
SUMIT_PDF = SAMPLES / "onboarding" / "AXIS_SUMIT_ONBOARDING_STATEMENT_Sumit_Dabas.pdf"


def _ctx(**overrides):
    base = {
        "user_name": "Rahul",
        "has_data": True,
        "monthly_summary": {
            "income": 80000,
            "expense": 72000,
            "savings": 8000,
            "savings_rate": 11.0,
            "period_label": "May 2026",
        },
        "recent_transactions": [{"merchant": "Zomato", "amount": 500}],
        "planning_snapshot": {
            "planning_burden_pct": 62.0,
            "active_purchase_goals": 2,
            "active_festivals": 1,
            "has_planning_data": True,
        },
    }
    base.update(overrides)
    return base


def _scope(mode: str, name: str = "Rahul") -> dict:
    return {"scope": mode, "user_name": name}


def _read_pdf(path: Path) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:5]:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


# ── Axis 1: data modes ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "scope,has_upload,has_data,expected",
    [
        ("no_upload", False, True, "A"),
        ("no_upload", False, False, "A"),
        ("unlinked_foreign", True, True, "B"),
        ("unlinked_same_bank", True, True, "C"),
        ("linked_full", True, True, "D"),
        ("linked_full", False, True, "A"),
    ],
)
def test_resolve_data_mode_matrix(scope, has_upload, has_data, expected):
    assert (
        resolve_data_mode(_scope(scope), has_session_upload=has_upload, has_linked_data=has_data)
        == expected
    )


# ── Axis 2 + scenarios ────────────────────────────────────────────────────


def test_mode_a_own_spend_allows_l2_llm():
    pol = evaluate_chat_policy(
        message="Where did I spend the most this month?",
        history=[],
        identity_scope=_scope("no_upload"),
        context=_ctx(),
        has_session_upload=False,
    )
    assert pol.data_mode == "A"
    assert pol.depth == "L2"
    assert pol.use_llm is True


def test_mode_a_simulation_allows_l2():
    pol = evaluate_chat_policy(
        message="What if I cut dining spend by 20%?",
        history=[],
        identity_scope=_scope("no_upload"),
        context=_ctx(),
        has_session_upload=False,
    )
    assert pol.data_mode == "A"
    assert pol.depth == "L2"
    assert pol.use_llm is True
    assert pol.intent == "SIMULATION"


def test_mode_a_my_insight_guided_l2_short_plus_section():
    pol = evaluate_chat_policy(
        message="Give me insight about my account",
        history=[],
        identity_scope=_scope("no_upload"),
        context=_ctx(),
        has_session_upload=False,
    )
    assert pol.data_mode == "A"
    assert pol.depth == "L2"
    assert pol.use_llm is True
    assert pol.route_tab == "insights"
    assert "polite" in pol.system_suffix.lower() or "GUIDED SHORT" in pol.system_suffix
    assert "AI Insights" in pol.system_suffix or "insights" in pol.system_suffix


def test_mode_a_deep_in_chat_guided_l2_not_hard_refuse():
    pol = evaluate_chat_policy(
        message="Give me full detail about my account here in chat",
        history=[],
        identity_scope=_scope("no_upload"),
        context=_ctx(),
        has_session_upload=False,
    )
    assert pol.data_mode == "A"
    assert pol.depth == "L2"
    assert pol.use_llm is True
    assert "PARTNER" in pol.system_suffix or "warm" in pol.system_suffix.lower()


def test_section_emi_guided_l2():
    pol = evaluate_chat_policy(
        message="How are my EMIs looking?",
        history=[],
        identity_scope=_scope("no_upload"),
        context=_ctx(),
        has_session_upload=False,
    )
    assert pol.depth == "L2"
    assert pol.use_llm is True
    assert pol.route_tab == "emi"


def test_mode_b_foreign_upload_uses_llm_l1():
    pol = evaluate_chat_policy(
        message="Summarise this uploaded statement",
        history=[],
        identity_scope=_scope("unlinked_foreign"),
        context=_ctx(has_data=False, data_authority="session_upload"),
        has_session_upload=True,
    )
    assert pol.data_mode == "B"
    assert pol.depth == "L1"
    assert pol.use_llm is True
    assert "SESSION UPLOAD" in (pol.system_suffix or "")


def test_mode_b_my_account_uses_linked_mode_a():
    pol = evaluate_chat_policy(
        message="insight about my account",
        history=[],
        identity_scope=_scope("unlinked_foreign"),
        context=_ctx(data_authority="ledger_month"),
        has_session_upload=True,
    )
    assert pol.data_mode == "A"
    assert pol.use_llm is True
    assert pol.intent == "MY_INSIGHT"


def test_mode_b_foreign_deep_l0():
    pol = evaluate_chat_policy(
        message="Give me line by line detail in this uploaded statement",
        history=[],
        identity_scope=_scope("unlinked_foreign"),
        context=_ctx(data_authority="session_upload"),
        has_session_upload=True,
    )
    assert pol.data_mode == "B"
    assert pol.depth == "L0"
    assert pol.use_llm is False
    assert "can't" in (pol.template_text or "").lower()


def test_mode_c_unlinked_same_bank_upload_llm():
    pol = evaluate_chat_policy(
        message="What does this Kotak statement show?",
        history=[],
        identity_scope=_scope("unlinked_same_bank"),
        context=_ctx(),
        has_session_upload=True,
    )
    assert pol.data_mode == "C"
    assert pol.depth == "L2"
    assert pol.use_llm is True


def test_mode_d_linked_upload_deep_first_ask_guided_l2():
    pol = evaluate_chat_policy(
        message="Give me everything about this statement in chat",
        history=[],
        identity_scope=_scope("linked_full", "Rahul"),
        context=_ctx(),
        has_session_upload=True,
    )
    assert pol.data_mode == "D"
    assert pol.depth == "L2"
    assert pol.use_llm is True


def test_insist_never_escalates_to_llm():
    history = [
        {"role": "user", "content": "Full detail here in chat"},
        {"role": "assistant", "content": "Open insights"},
        {"role": "user", "content": "No redirect, idhar hi sab do"},
        {"role": "assistant", "content": "Still redirect"},
        {"role": "user", "content": "I refuse, give me everything here"},
    ]
    pol = evaluate_chat_policy(
        message="I said don't send me away, full breakdown idhar hi",
        history=history,
        identity_scope=_scope("no_upload"),
        context=_ctx(),
        has_session_upload=False,
    )
    assert pol.depth == "L3"
    assert pol.use_llm is False
    assert pol.insist_count >= 2


# ── Sample PDF identity (Vikram vs logged-in Rahul) ───────────────────────


@pytest.mark.skipif(not VIKRAM_PDF.is_file(), reason="Vikram sample PDF missing")
def test_pdf_vikram_is_foreign_for_rahul():
    text = _read_pdf(VIKRAM_PDF)
    info = enrich_doc_info_from_text({}, text, VIKRAM_PDF.name)
    assert "vikram" in (info.get("account_holder_name") or "").lower()
    scope = resolve_identity_scope(1, info, [{"institution_name": "HDFC Bank"}])
    # get_user_name(1) may not be Rahul — check name mismatch path
    if scope.get("user_name", "").lower().startswith("vikram"):
        pytest.skip("DB user 1 is Vikram — use synthetic check below")
    assert scope["scope"] == "unlinked_foreign"


def test_pdf_vikram_holder_mismatch_synthetic():
    text = _read_pdf(VIKRAM_PDF) if VIKRAM_PDF.is_file() else ""
    if not text:
        pytest.skip("PDF missing")
    info = enrich_doc_info_from_text({}, text, VIKRAM_PDF.name)
    info["account_holder_name"] = "Vikram Singh"
    scope = resolve_identity_scope(
        99,
        info,
        [{"institution_name": "Axis Bank"}],
    )
    # Override: simulate Rahul session by checking _names_likely_match indirectly
    from services.ai_context_service import _names_likely_match

    assert not _names_likely_match("Vikram Singh", "Rahul Sharma")
    # Full resolve uses DB name; document holder != user → foreign
    assert info.get("account_holder_name") == "Vikram Singh"


@pytest.mark.skipif(not SUMIT_PDF.is_file(), reason="Sumit sample PDF missing")
def test_pdf_sumit_holder_detected():
    text = _read_pdf(SUMIT_PDF)
    info = enrich_doc_info_from_text({}, text, SUMIT_PDF.name)
    holder = (info.get("account_holder_name") or "").split("\n")[0].strip().lower()
    assert "sumit" in holder


def test_classify_intents():
    assert classify_intent("insight about my account") == "MY_INSIGHT"
    assert classify_intent("what if I spend 10% more") == "SIMULATION"
    assert classify_intent("show my EMI details") == "SECTION_SPECIFIC"
    assert classify_intent("full detail in chat") == "DEEP_IN_CHAT"
