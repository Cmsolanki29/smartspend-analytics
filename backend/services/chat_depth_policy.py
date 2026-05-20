"""
Chat depth policy — preserve app section value; never dump full account detail in chat.

Depth levels:
  L0 block | L1 micro (foreign upload) | L2 short chat | L3 redirect (3–4 lines + ROUTE)
Insistence on deep-in-chat always stays L3 (extra lines only), never escalates to L4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ChatPolicy:
    use_llm: bool
    template_text: str | None = None
    max_words: int = 110
    route_tab: str = "insights"
    route_label: str = "Open AI Insights"
    intent: str = "GENERAL"
    depth: str = "L2"
    data_mode: str = "A"
    insist_count: int = 0
    system_suffix: str = ""

    def to_meta(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "depth": self.depth,
            "data_mode": self.data_mode,
            "max_words": self.max_words,
            "route_tab": self.route_tab,
            "insist_count": self.insist_count,
        }


def resolve_data_mode(
    identity_scope: dict[str, Any],
    *,
    has_session_upload: bool,
    has_linked_data: bool,
) -> str:
    """
    Axis 1 — explicit data source for policy + logging.

    A: own linked ledger (no foreign upload in session)
    B: session upload, foreign holder (unlinked_foreign)
    C: session upload, same person, bank not linked (unlinked_same_bank)
    D: session upload, name + bank match linked (linked_full)
    """
    scope = identity_scope.get("scope") or "no_upload"
    if scope == "unlinked_foreign":
        return "B"
    if scope == "unlinked_same_bank":
        return "C"
    if scope == "linked_full" and has_session_upload:
        return "D"
    if has_linked_data or scope in ("no_upload", "linked_full"):
        return "A"
    return "A"


_DEEP_RE = re.compile(
    r"(?i)\b("
    r"detail(?:ed)?|full\s+(?:detailed\s+)?(?:insight|analysis|breakdown|report)|everything|complete\s+overview|"
    r"line\s*by\s*line|all\s+transactions|merchant\s*wise|every\s+transaction|"
    r"whole\s+(?:statement|account|document)|entire\s+account|dump\s+everything|"
    r"idhar\s+hi|yahi\s+pe|in\s+this\s+chat|here\s+in\s+chat|only\s+in\s+chat|"
    r"don'?t\s+redirect|no\s+redirect|stop\s+redirecting|"
    r"bata\s+saara|poora\s+bata|sab\s+kuch\s+bata|puri\s+detail"
    r")\b",
)

_INSIST_RE = re.compile(
    r"(?i)\b("
    r"still\s+want|i\s+said|told\s+you|already\s+asked|give\s+me\s+here|"
    r"refuse|won'?t\s+go|not\s+going\s+to|idhar\s+hi\s+chahiye|chat\s+mein\s+hi|"
    r"no\s+button|without\s+leaving|don'?t\s+send\s+me\s+away"
    r")\b",
)

_INSIGHT_PAGE_RE = re.compile(
    r"(?i)\b(insight(?:s)?\s+about\s+my\s+account|my\s+account\s+insight|financial\s+overview|"
    r"overall\s+financial\s+health|full\s+coach|health\s+score\s+explain)\b",
)

_SECTION_ROUTES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"(?i)\b(emis?|loan|installment)\b"), "emi", "Open EMI Tracker"),
    (re.compile(r"(?i)\b(fraud|suspicious|scam|unusual\s+txn)\b"), "fraud", "Open FraudShield"),
    (re.compile(r"(?i)\b(subscription|netflix|spotify|recurring)\b"), "subscriptions", "Open Subscriptions"),
    (re.compile(r"(?i)\b(purchase\s+goal|buy\s+phone|laptop\s+goal)\b"), "purchase", "Open Purchase Planner"),
    (re.compile(r"(?i)\b(festival|diwali|event\s+plan)\b"), "festival", "Open Festival Planner"),
    (re.compile(r"(?i)\b(transaction|spend(?:ing)?\s+breakdown|merchant|category)\b"), "transactions", "Open Transactions"),
]


def _fmt_inr(v: float) -> str:
    try:
        n = float(v or 0)
        if n >= 100000:
            return f"₹{n/100000:.2f}L".replace(".00L", "L")
        return f"₹{int(round(n)):,}"
    except (TypeError, ValueError):
        return "₹0"


def _teaser_lines(context: dict[str, Any], *, max_lines: int = 3) -> list[str]:
    """At most 3 factual lines from context — never a full statement dump."""
    ms = context.get("monthly_summary") or {}
    lines: list[str] = []
    inc = float(ms.get("income") or 0)
    exp = float(ms.get("expense") or 0)
    sav = float(ms.get("savings") or 0)
    rate = float(ms.get("savings_rate") or 0)
    period = ms.get("period_label") or context.get("period_label") or "this period"
    if inc > 0 or exp > 0:
        lines.append(
            f"{period}: credits {_fmt_inr(inc)}, debits {_fmt_inr(exp)}, net {_fmt_inr(sav)}."
        )
    if rate != 0 or (inc > 0 and sav != 0):
        lines.append(f"Approx. savings rate: {rate:.1f}%." if rate else f"Net position: {_fmt_inr(sav)}.")
    txns = context.get("recent_transactions") or []
    if txns:
        top = sorted(txns, key=lambda t: float(t.get("amount") or 0), reverse=True)[:1]
        if top:
            t0 = top[0]
            lines.append(
                f"Largest recent line item: {_fmt_inr(float(t0.get('amount') or 0))} "
                f"at {(t0.get('merchant') or t0.get('description') or 'a merchant')[:40]}."
            )
    return lines[:max_lines]


def _route_line(tab: str, label: str) -> str:
    return f'ROUTE:{{"label":"{label} →","path":"/{tab}","tab":"{tab}"}}'


def _chips(*items: str) -> str:
    return "CHIPS:" + "|".join(items[:3])


def _resolve_section_route(message: str) -> tuple[str, str]:
    for pat, tab, label in _SECTION_ROUTES:
        if pat.search(message):
            return tab, label
    return "insights", "Open AI Insights"


def _section_display_name(route_label: str) -> str:
    return route_label.replace("Open ", "").strip() or "the app section"


def _guided_l2_suffix(
    *,
    user_name: str,
    data_mode: str,
    tab: str,
    route_label: str,
    intent: str,
    context: dict[str, Any],
    teasers: list[str],
) -> str:
    """
    Short helpful answer first, then polite pointer to the dedicated app section.
    Applies to Insights, EMI, Subscriptions, Transactions, Purchase, Festival, etc.
    """
    section = _section_display_name(route_label)
    mode_note = (
        "Mode D: session upload matches linked bank — use packet totals for this file."
        if data_mode == "D"
        else "Mode A: use linked ledger context."
    )
    facts = "; ".join(teasers[:2]) if teasers else ""
    planning = context.get("planning_snapshot") or {}
    planning_note = ""
    if planning.get("has_planning_data") and intent in ("MY_INSIGHT", "OWN_OVERVIEW", "GENERAL"):
        planning_note = (
            f" Planning load ~{planning.get('planning_burden_pct')}% of income "
            f"({planning.get('active_purchase_goals', 0)} purchase goals, "
            f"{planning.get('active_festivals', 0)} festivals)."
        )
    insight_extra = ""
    if intent == "MY_INSIGHT":
        insight_extra = (
            f' Point them to **AI Insights** for the full coach (health score, warnings, quick wins). '
            f'Section name in polite line: "{section}".'
        )
    return (
        "\n\n═══ PARTNER REPLY (warm, not robotic) ═══\n"
        f"- {mode_note} User: {user_name}.\n"
        "- You are their SmartSpend Partner — confident, friendly, Hinglish OK if they use it.\n"
        "- STRUCTURE:\n"
        "  1) Lead with 2–4 helpful sentences using ONLY context numbers (answer first).\n"
        f"  2) One soft line: deeper charts live in {section} — optional, not preachy.\n"
        f"  3) {_route_line(tab, route_label)}\n"
        "  4) CHIPS: 2–3 short follow-ups.\n"
        "- Max ~110 words before ROUTE/CHIPS. No line-by-line statement dump (no L4).\n"
        f"{insight_extra}"
        + (f"- Facts to use: {facts}.{planning_note}\n" if facts or planning_note else "")
    )


def _insist_l3_suffix(
    *,
    user_name: str,
    tab: str,
    route_label: str,
    teasers: list[str],
) -> str:
    section = _section_display_name(route_label)
    facts = "; ".join(teasers[:3]) if teasers else ""
    return (
        "\n\n═══ USER INSISTED ON MORE IN CHAT (stay partner, not cold template) ═══\n"
        f"- User: {user_name}. They asked again — acknowledge briefly (e.g. I hear you).\n"
        "- Give 3–4 extra factual bullets from context only — still NO full dump.\n"
        f"- Then one warm line: the richest view is in {section}; you're not refusing help.\n"
        f"- End {_route_line(tab, route_label)} + CHIPS.\n"
        f"- Max ~120 words. Facts: {facts or 'use context packet'}.\n"
    )


def _count_deep_insistence(history: list[dict], message: str) -> int:
    n = 0
    for h in history:
        if h.get("role") != "user":
            continue
        text = str(h.get("content") or "")
        if _DEEP_RE.search(text) or _INSIST_RE.search(text):
            n += 1
    if _DEEP_RE.search(message) or _INSIST_RE.search(message):
        n += 1
    return max(0, n - 1)


_UPLOAD_FOCUS_RE = re.compile(
    r"(?i)\b("
    r"this\s+(?:statement|file|document|pdf|upload|image)|uploaded\s+(?:file|statement|pdf|image)|"
    r"in\s+this\s+(?:statement|file)|from\s+this\s+(?:statement|file|upload)|that\s+statement|"
    r"the\s+statement\s+i\s+uploaded|parsed\s+file|axis\s+statement|"
    r"unusual.*statement|suspicious.*statement|transactions?\s+in\s+this|"
    r"summar(?:y|ise).*statement|analyze.*statement|analyse.*statement"
    r")\b",
)


def message_targets_upload(message: str) -> bool:
    return bool(_UPLOAD_FOCUS_RE.search(message or ""))


def has_linked_ledger_context(context: dict[str, Any]) -> bool:
    auth = context.get("data_authority") or ""
    return auth in ("ledger_month", "ledger_90d", "latest_ledger_upload")


def _session_upload_suffix(
    *,
    user_name: str,
    data_mode: str,
    context: dict[str, Any],
    foreign: bool,
) -> str:
    su = context.get("session_upload") or {}
    doc = su.get("doc_info") or {}
    inst = doc.get("institution_name") or "uploaded file"
    holder = doc.get("account_holder_name") or "unknown"
    n = int(su.get("transaction_count") or 0)
    foreign_note = (
        "This file belongs to a different person — use ONLY session_upload numbers; "
        "do not mix with linked ledger."
        if foreign
        else "Same person, bank may not be linked — prefer session_upload for file questions."
    )
    return (
        "\n\n═══ SESSION UPLOAD (file in chat) ═══\n"
        f"- {foreign_note}\n"
        f"- Institution: {inst}; holder on file: {holder}; rows: {n}.\n"
        f"- User: {user_name}. Mode {data_mode}. Warm partner tone; max ~90 words before ROUTE/CHIPS.\n"
        "- Answer the question about THIS file only; 2–3 facts from session_upload / health_preview.\n"
        "- If transaction_count is 0, say the image/PDF wasn't readable and suggest PDF/CSV or Connect Account.\n"
    )


def classify_intent(message: str) -> str:
    msg = message or ""
    if _INSIGHT_PAGE_RE.search(msg):
        return "MY_INSIGHT"
    if _DEEP_RE.search(msg):
        return "DEEP_IN_CHAT"
    for pat, _, _ in _SECTION_ROUTES:
        if pat.search(msg):
            return "SECTION_SPECIFIC"
    if re.search(r"(?i)\b(what\s+if|simulate|cut\s+\d+|spend\s+\d+%\s+more)\b", msg):
        return "SIMULATION"
    if re.search(r"(?i)\b(my\s+account|my\s+spend|my\s+savings|where\s+did\s+i\s+spend)\b", msg):
        return "OWN_OVERVIEW"
    return "GENERAL"


def evaluate_chat_policy(
    *,
    message: str,
    history: list[dict],
    identity_scope: dict[str, Any],
    context: dict[str, Any],
    has_session_upload: bool,
) -> ChatPolicy:
    """
    Decide whether to use LLM or a fixed template, and cap depth.
    """
    scope = identity_scope.get("scope") or "no_upload"
    user_name = (identity_scope.get("user_name") or context.get("user_name") or "there").strip()
    first = user_name.split()[0] if user_name else "there"
    intent = classify_intent(message)
    insist = _count_deep_insistence(history, message)
    tab, route_label = _resolve_section_route(message)
    teasers = _teaser_lines(context, max_lines=3)
    linked_ledger = has_linked_ledger_context(context)
    data_mode = resolve_data_mode(
        identity_scope,
        has_session_upload=has_session_upload,
        has_linked_data=linked_ledger or bool(context.get("has_data")),
    )
    upload_focus = message_targets_upload(message)
    # Linked ledger wins for any non-upload question (foreign file stays in session only).
    if linked_ledger and not upload_focus:
        data_mode = "A"

    def _policy(**kwargs: Any) -> ChatPolicy:
        base = {
            "insist_count": insist,
            "data_mode": data_mode,
        }
        base.update(kwargs)
        return ChatPolicy(**base)

    # Mode B but question is about linked account (upload_focus false) → treat as A
    if data_mode == "B" and not upload_focus and linked_ledger:
        data_mode = "A"

    # ── Mode B — foreign upload in session: partner LLM on file; block line-by-line dumps ──
    if data_mode == "B" and upload_focus:
        if _DEEP_RE.search(message) or intent == "DEEP_IN_CHAT":
            body = (
                f"{first}, I can't dump someone else's statement line-by-line in chat — that's by design.\n"
                f"Here's a quick snapshot from the upload only; open your linked account for your full coach.\n\n"
                f"{_route_line('settings', 'Connect Account')}\n\n"
                f"{_chips('About my linked account', 'My savings rate', 'Top spend this month')}"
            )
            return _policy(
                use_llm=False,
                template_text=body,
                intent="FOREIGN_DEEP_BLOCK",
                depth="L0",
                route_tab="settings",
                route_label="Connect Account",
            )
        return _policy(
            use_llm=True,
            max_words=95,
            route_tab="settings",
            route_label="Connect Account",
            intent="FOREIGN_UPLOAD",
            depth="L1",
            system_suffix=_session_upload_suffix(
                user_name=user_name,
                data_mode="B",
                context=context,
                foreign=True,
            ),
        )

    # ── Mode C — same person, bank not linked: LLM on session file ──
    if data_mode == "C" and upload_focus:
        if insist > 0 and _DEEP_RE.search(message):
            return _policy(
                use_llm=False,
                template_text=(
                    f"{first}, connect this bank in Settings for the full chart view — "
                    f"chat stays a quick layer.\n\n"
                    f"{_route_line('settings', 'Connect Account')}\n\n"
                    f"{_chips('My linked summary', 'Savings rate', 'EMI check')}"
                ),
                intent="UNLINKED_DEEP",
                depth="L3",
                route_tab="settings",
            )
        return _policy(
            use_llm=True,
            max_words=100,
            route_tab="settings",
            route_label="Connect Account",
            intent="UNLINKED_UPLOAD",
            depth="L2",
            system_suffix=_session_upload_suffix(
                user_name=user_name,
                data_mode="C",
                context=context,
                foreign=False,
            ),
        )

    # MY_INSIGHT → always route tease to AI Insights page
    if intent == "MY_INSIGHT":
        tab, route_label = "insights", "Open AI Insights"

    # ── Insist: partner LLM with extra facts (modes A/C/D); template only if no ledger ──
    if insist > 0 and data_mode in ("A", "C", "D") and linked_ledger:
        return _policy(
            use_llm=True,
            max_words=120,
            route_tab=tab,
            route_label=route_label,
            intent=intent,
            depth="L3",
            system_suffix=_insist_l3_suffix(
                user_name=user_name,
                tab=tab,
                route_label=route_label,
                teasers=teasers,
            ),
        )
    if insist > 0:
        section = _section_display_name(route_label)
        bullet = "\n".join(f"• {ln}" for ln in teasers[:2]) if teasers else ""
        body = (
            f"Hey {first}, I hear you — here's a bit more:\n{bullet or '• See the app section for live numbers.'}\n\n"
            f"For the **full** charts and history, **{section}** has the complete view — chat stays your quick layer.\n\n"
            f"{_route_line(tab, route_label)}\n\n"
            f"{_chips('Top expenses this month', 'How are my EMIs?', 'Open AI Insights')}"
        )
        return _policy(
            use_llm=False,
            template_text=body,
            intent=intent,
            depth="L3",
            route_tab=tab,
            route_label=route_label,
        )

    # ── Guided L2: short answer + polite “visit section for more” (Insights, EMI, Subs, …) ──
    guided_intents = ("MY_INSIGHT", "SECTION_SPECIFIC", "DEEP_IN_CHAT", "OWN_OVERVIEW")
    if intent in guided_intents or intent == "GENERAL":
        return _policy(
            use_llm=True,
            max_words=100,
            route_tab=tab,
            route_label=route_label,
            intent=intent,
            depth="L2",
            system_suffix=_guided_l2_suffix(
                user_name=user_name,
                data_mode=data_mode,
                tab=tab,
                route_label=route_label,
                intent=intent,
                context=context,
                teasers=teasers,
            ),
        )

    # ── Mode A / D — L2: simulations & general capped chat ──
    suffix = _guided_l2_suffix(
        user_name=user_name,
        data_mode=data_mode,
        tab=tab,
        route_label=route_label,
        intent=intent,
        context=context,
        teasers=teasers,
    )
    if intent == "SIMULATION":
        suffix += "- Simulation: one scenario, projected ₹ impact, max 2 figures.\n"
    return _policy(
        use_llm=True,
        max_words=110,
        route_tab=tab,
        route_label=route_label,
        intent=intent,
        depth="L2",
        system_suffix=suffix,
    )


def enforce_output_cap(text: str, policy_meta: dict[str, Any] | None) -> str:
    """Post-LLM trim: prevent accidental long dumps."""
    if not text:
        return text
    meta = policy_meta or {}
    max_words = int(meta.get("max_words") or 110)
    tab = meta.get("route_tab") or "insights"
    label = "Open AI Insights" if tab == "insights" else f"Open {tab.replace('-', ' ').title()}"

    clean = re.sub(r"ROUTE:\{[^\n}]+\}", "", text)
    clean = re.sub(r"CHIPS:[^\n]+", "", clean)
    words = clean.split()
    if len(words) > max_words:
        trimmed = " ".join(words[:max_words]).rstrip() + "…"
        route = _route_line(tab, label)
        chips = _chips("Open AI Insights", "Top expenses", "EMI check")
        text = f"{trimmed}\n\nFull detail is in the app section.\n{route}\n\n{chips}"

    # Strip CHIPS/ROUTE duplication if model over-generated lists
    lines = text.split("\n")
    if len(lines) > 14:
        text = "\n".join(lines[:14]) + "\n\n" + _route_line(tab, label)
    return text
