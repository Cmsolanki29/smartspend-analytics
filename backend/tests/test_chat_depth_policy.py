"""Chat depth policy — insistence never unlocks full detail in chat."""

from services.chat_depth_policy import evaluate_chat_policy, enforce_output_cap


def _ctx():
    return {
        "user_name": "Rahul",
        "has_data": True,
        "monthly_summary": {
            "income": 80000,
            "expense": 72000,
            "savings": 8000,
            "savings_rate": 10.0,
            "period_label": "May 2026",
        },
        "recent_transactions": [
            {"merchant": "Zomato", "amount": 500, "description": "Zomato"},
        ],
    }


def test_foreign_deep_blocked_without_llm():
    pol = evaluate_chat_policy(
        message="Give me full detailed breakdown of this statement",
        history=[],
        identity_scope={"scope": "unlinked_foreign", "user_name": "Rahul"},
        context=_ctx(),
        has_session_upload=True,
    )
    assert pol.use_llm is False
    assert pol.depth == "L0"
    assert "Connect Account" in (pol.template_text or "")


def test_own_deep_first_ask_guided_l2():
    pol = evaluate_chat_policy(
        message="Give me all details about my account here in chat only",
        history=[],
        identity_scope={"scope": "no_upload", "user_name": "Rahul"},
        context=_ctx(),
        has_session_upload=False,
    )
    assert pol.use_llm is True
    assert pol.depth == "L2"
    assert "PARTNER" in pol.system_suffix or "warm" in pol.system_suffix.lower()


def test_insist_stays_redirect():
    history = [
        {"role": "user", "content": "Give me full detail here in chat"},
        {"role": "assistant", "content": "Please open AI Insights"},
        {"role": "user", "content": "No I refuse, tell me everything idhar hi"},
    ]
    ctx = _ctx()
    ctx["data_authority"] = "ledger_month"
    pol = evaluate_chat_policy(
        message="I said idhar hi, don't redirect",
        history=history,
        identity_scope={"scope": "no_upload", "user_name": "Rahul"},
        context=ctx,
        has_session_upload=False,
    )
    assert pol.insist_count >= 1
    assert pol.depth == "L3"
    assert pol.use_llm is True
    assert "INSISTED" in (pol.system_suffix or "")


def test_output_cap_truncates_long_llm():
    long = "word " * 200 + '\nROUTE:{"label":"X","tab":"insights"}'
    out = enforce_output_cap(long, {"max_words": 110, "route_tab": "insights"})
    assert len(out.split()) < 250
    assert "ROUTE:" in out
