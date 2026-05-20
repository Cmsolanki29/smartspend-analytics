"""
AI Context Service — assembles a compressed context packet for the AI chatbot.

Uses the existing psycopg2 sync DB layer (same as all other services in this project).
Never sends raw DB rows to the LLM — always compresses into a clean dict first.
"""
from __future__ import annotations

import calendar
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from db import get_connection
from services.dashboard_scope import normalize_dashboard_mode, transaction_scope_sql

_log = logging.getLogger(__name__)

_CACHE_TTL_MINUTES = 10
_LEDGER_LOOKBACK_DAYS = 90
_RECURRING_MERCHANT_HINTS = (
    "netflix",
    "spotify",
    "prime video",
    "hotstar",
    "youtube",
    "apple.com",
    "google play",
    "microsoft",
    "adobe",
    "linkedin",
)


def _rollback_conn(conn) -> None:
    try:
        conn.rollback()
    except Exception:
        pass


def get_user_name(user_id: int) -> str:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(NULLIF(TRIM(name), ''), 'there') FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return str(row[0]) if row else "there"
    except Exception:
        return "there"
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


def _fetch_connected_sources(cur, user_id: int) -> list[dict[str, Any]]:
    try:
        cur.execute(
            """
            SELECT institution_name, source_type,
                   COALESCE(status, 'active') AS status
            FROM connected_sources
            WHERE user_id = %s
              AND COALESCE(status, 'active') = 'active'
            ORDER BY is_primary DESC NULLS LAST, connected_at DESC NULLS LAST
            """,
            (user_id,),
        )
        return [
            {"institution_name": r[0] or "", "source_type": r[1] or ""}
            for r in cur.fetchall()
        ]
    except Exception as e:
        _rollback_conn(cur.connection)
        _log.warning("[ai_context] connected_sources fetch error: %s", e)
        return []


# Indian bank tokens — scored from document text (not from user profile).
_BANK_TEXT_SIGNALS: list[tuple[str, str, int]] = [
    (r"\bicici\s*bank\b", "ICICI Bank", 4),
    (r"\bicici\b", "ICICI Bank", 3),
    (r"\bhdfc\s*bank\b", "HDFC Bank", 4),
    (r"\bhdfc\b", "HDFC Bank", 3),
    (r"\bstate\s*bank\s*of\s*india\b", "State Bank of India", 4),
    (r"\bsbi\b", "State Bank of India", 2),
    (r"\baxis\s*bank\b", "Axis Bank", 4),
    (r"\baxis\b", "Axis Bank", 2),
    (r"\bkotak\b", "Kotak Mahindra Bank", 3),
    (r"\byes\s*bank\b", "Yes Bank", 3),
    (r"\bpunjab\s*national\b", "Punjab National Bank", 3),
    (r"\bcanara\s*bank\b", "Canara Bank", 3),
]

_HOLDER_TEXT_PATTERNS = [
    r"(?:account\s*holder|customer\s*name|name\s*of\s*account\s*holder|holder\s*name)"
    r"\s*[:\-]\s*([A-Za-z][A-Za-z\s.'-]{2,60})",
    r"(?:dear|mr\.?|mrs\.?|ms\.?|shri\.?|smt\.?)\s+([A-Za-z][A-Za-z\s.'-]{2,60})",
]

_FILENAME_SKIP_TOKENS = frozenset({
    "icici", "hdfc", "sbi", "axis", "kotak", "yes", "bank", "emi", "account",
    "statement", "loan", "credit", "card", "apr", "may", "jun", "jul", "aug",
    "sep", "oct", "nov", "dec", "jan", "feb", "mar", "pdf", "csv", "txt",
    "sample", "realistic", "fixed", "gen", "genz", "neo", "magnus", "ace",
})


def _bank_canonical_key(name: str | None) -> str | None:
    if not name:
        return None
    low = name.lower()
    for key in ("icici", "hdfc", "sbi", "axis", "kotak", "yes", "pnb", "canara"):
        if key in low:
            return key
    return None


def detect_institution_in_text(text: str) -> str | None:
    """Pick the bank most strongly mentioned in raw document text."""
    if not text or len(text.strip()) < 8:
        return None
    scores: dict[str, int] = {}
    for pattern, label, weight in _BANK_TEXT_SIGNALS:
        for _ in re.finditer(pattern, text, re.IGNORECASE):
            scores[label] = scores.get(label, 0) + weight
    if not scores:
        return None
    best_label, best_score = max(scores.items(), key=lambda x: x[1])
    if best_score < 2:
        return None
    return best_label


def detect_holder_in_text(text: str) -> str | None:
    if not text:
        return None
    for pattern in _HOLDER_TEXT_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if len(name) >= 3 and not name.lower().startswith("icici"):
                return name.title()
    return None


def detect_institution_in_filename(filename: str) -> str | None:
    """Weak fallback when body text has no bank string — filename token only, not user profile."""
    if not filename:
        return None
    low = filename.lower()
    for key, label in (
        ("icici", "ICICI Bank"),
        ("hdfc", "HDFC Bank"),
        ("axis", "Axis Bank"),
        ("kotak", "Kotak Mahindra Bank"),
        ("sbi", "State Bank of India"),
        ("yesbank", "Yes Bank"),
        ("yes_bank", "Yes Bank"),
    ):
        if key in low.replace("-", "_"):
            return label
    return None


def detect_holder_in_filename(filename: str) -> str | None:
    """First name-like token in filename (e.g. RAHUL_ICICI_EMI → Rahul). Bank names excluded."""
    if not filename:
        return None
    stem = Path(filename).stem
    for part in re.split(r"[_\-\s]+", stem):
        token = part.strip()
        if len(token) < 3 or not token.isalpha():
            continue
        low = token.lower()
        if low in _FILENAME_SKIP_TOKENS:
            continue
        return token.title()
    return None


def enrich_doc_info_from_text(
    doc_info: dict[str, Any],
    raw_text: str,
    filename: str = "",
) -> dict[str, Any]:
    """
    Correct LLM metadata using deterministic signals from document body + filename holder hint.
    Institution always prefers explicit mentions in raw_text over LLM guesses.
    """
    info = dict(doc_info or {})
    text_inst = detect_institution_in_text(raw_text)
    llm_inst = (info.get("institution_name") or "").strip() or None

    fn_inst = detect_institution_in_filename(filename)

    if text_inst:
        llm_key = _bank_canonical_key(llm_inst)
        text_key = _bank_canonical_key(text_inst)
        if not llm_inst or (llm_key and text_key and llm_key != text_key):
            if llm_inst and llm_key != text_key:
                _log.warning(
                    "Overriding LLM institution %r → %r (from document text)",
                    llm_inst,
                    text_inst,
                )
            info["institution_name"] = text_inst
    elif fn_inst:
        if llm_inst and _bank_canonical_key(llm_inst) != _bank_canonical_key(fn_inst):
            _log.warning(
                "Overriding LLM institution %r → %r (from filename token; no bank in text)",
                llm_inst,
                fn_inst,
            )
        info["institution_name"] = fn_inst
    elif llm_inst:
        info["institution_name"] = llm_inst

    holder = (info.get("account_holder_name") or "").strip() or None
    if not holder:
        holder = detect_holder_in_text(raw_text)
    if not holder:
        holder = detect_holder_in_filename(filename)
    if holder:
        info["account_holder_name"] = holder

    _log.info(
        "enrich_doc_info: institution=%r holder=%r (filename=%r)",
        info.get("institution_name"),
        info.get("account_holder_name"),
        filename[:80] if filename else "",
    )
    return info


def _names_likely_match(doc_name: str | None, user_name: str | None) -> bool:
    """
    True = same person or cannot determine (permissive).
    False = clearly different person.
    """
    if not doc_name or not user_name:
        return True

    doc_clean = doc_name.strip().lower()
    user_clean = user_name.strip().lower()

    if doc_clean == user_clean:
        return True

    if not doc_clean.isascii():
        return True

    stop = {"mr", "mrs", "ms", "dr", "shri", "smt"}
    doc_words = set(doc_clean.split()) - stop
    user_words = set(user_clean.split()) - stop

    if doc_words & user_words:
        return True

    doc_initials = "".join(w[0] for w in doc_clean.split() if w)
    user_initials = "".join(w[0] for w in user_clean.split() if w)
    if doc_initials == user_initials and len(doc_initials) >= 2:
        return True

    return False


def resolve_identity_scope(
    user_id: int,
    doc_info: dict | None,
    connected_sources: list[dict],
) -> dict[str, Any]:
    """Determines data scope and relationship of an uploaded document to this user."""
    user_name = get_user_name(user_id)
    linked_bank_names = [
        s["institution_name"]
        for s in connected_sources
        if s.get("institution_name")
    ]

    if not doc_info:
        return {
            "scope": "no_upload",
            "reason": None,
            "warning_message": None,
            "nudge_message": None,
            "linked_bank_names": linked_bank_names,
            "user_name": user_name,
        }

    doc_holder = doc_info.get("account_holder_name")
    if isinstance(doc_holder, str):
        doc_holder = doc_holder.strip() or None
    doc_bank = (doc_info.get("institution_name") or "").strip()
    doc_bank_label = doc_bank or "this bank"

    name_matches = _names_likely_match(doc_holder, user_name)
    _log.info(
        "Identity check: user=%s, doc_holder=%s → %s",
        user_name,
        doc_holder or "(not in document)",
        "MATCH" if name_matches else "MISMATCH",
    )

    if not name_matches:
        scope = {
            "scope": "unlinked_foreign",
            "reason": "different_person",
            "warning_message": (
                f"Hey {(user_name or 'there').split()[0]}, this statement looks like it belongs to someone else — "
                f"I'll only use it for a **short** preview of that file. "
                f"Ask about **your linked account** anytime for personalised insights."
            ),
            "nudge_message": "Please link your account in Connected Accounts.",
            "linked_bank_names": linked_bank_names,
            "user_name": user_name,
        }
        _log.info(
            "resolve_identity_scope: scope=%s reason=%s",
            scope["scope"],
            scope["reason"],
        )
        return scope

    doc_bank_lower = doc_bank.lower()
    is_bank_linked = bool(
        doc_bank_lower
        and doc_bank_lower not in ("unknown",)
        and any(
            doc_bank_lower in (name or "").lower() or (name or "").lower() in doc_bank_lower
            for name in linked_bank_names
        )
    )

    if is_bank_linked:
        # Name matches AND bank matches a connected source → full access
        scope = {
            "scope": "linked_full",
            "reason": "name_and_bank_match",
            "warning_message": None,
            "nudge_message": None,
            "linked_bank_names": linked_bank_names,
            "user_name": user_name,
        }
        _log.info("resolve_identity_scope: scope=%s reason=%s", scope["scope"], scope["reason"])
        return scope

    # Name matches but bank is NOT in the user's connected sources → different bank
    scope = {
        "scope": "unlinked_same_bank",
        "reason": "different_bank_not_connected",
        "warning_message": (
            f"Hello {user_name}, this seems to be a different bank account. "
            f"I'll provide insights but link this account for full access."
        ),
        "nudge_message": "Link this account in Connected Accounts for full tracking and trends.",
        "linked_bank_names": linked_bank_names,
        "user_name": user_name,
    }
    _log.info("resolve_identity_scope: scope=%s reason=%s", scope["scope"], scope["reason"])
    return scope


def extract_all_amounts_from_context(context_packet: dict) -> list[float]:
    amounts: list[float] = []

    def _add(v: Any) -> None:
        try:
            amounts.append(float(v))
        except (TypeError, ValueError):
            pass

    ms = context_packet.get("monthly_summary") or {}
    for k in ("income", "expense", "savings"):
        _add(ms.get(k))
    for cat_amt in (ms.get("categories") or {}).values():
        _add(cat_amt)

    for txn in context_packet.get("recent_transactions") or []:
        _add(txn.get("amount"))
    for emi in context_packet.get("active_emis") or []:
        _add(emi.get("amount"))
    for sub in context_packet.get("subscriptions") or []:
        _add(sub.get("amount"))

    su = context_packet.get("session_upload") or {}
    for txn in su.get("transactions") or []:
        _add(txn.get("amount"))
    hp = su.get("health_preview") or {}
    for k in ("total_debits", "total_credits", "net", "top_spending_amount"):
        _add(hp.get(k))

    return amounts


def invalidate_user_ai_context_cache(user_id: int) -> None:
    """Clear cached context for all AI sessions belonging to this user (after ledger upload)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE ai_sessions
            SET cached_context = NULL,
                context_built_at = NULL,
                cache_dashboard_scope = NULL,
                cache_context_month = NULL,
                cache_context_year = NULL
            WHERE user_id = %s
            """,
            (user_id,),
        )
        conn.commit()
    except Exception as e:
        _log.warning("[ai_context] user cache invalidate failed: %s", e)
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


def invalidate_session_context_cache(session_id: str) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE ai_sessions
            SET cached_context = NULL,
                context_built_at = NULL,
                cache_dashboard_scope = NULL,
                cache_context_month = NULL,
                cache_context_year = NULL
            WHERE id = %s::uuid
            """,
            (session_id,),
        )
        conn.commit()
    except Exception as e:
        _log.warning("[ai_context] cache invalidate failed: %s", e)
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


def calculate_quick_health(transactions: list[dict]) -> dict[str, Any]:
    """Quick health snapshot from session-only uploaded transactions."""
    debits = 0.0
    credits = 0.0
    categories: dict[str, float] = {}
    for txn in transactions:
        try:
            amount = float(txn.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if str(txn.get("type", "debit")).lower() == "credit":
            credits += amount
        else:
            debits += amount
            cat = str(txn.get("category") or "other")
            categories[cat] = categories.get(cat, 0.0) + amount

    net = credits - debits
    savings_rate = round(net / credits * 100, 1) if credits > 0 else 0.0
    top_cat: tuple[str, float] | None = None
    if categories:
        top_cat = max(categories.items(), key=lambda x: x[1])

    return {
        "total_debits": round(debits, 2),
        "total_credits": round(credits, 2),
        "net": round(net, 2),
        "savings_rate_pct": savings_rate,
        "transaction_count": len(transactions),
        "top_spending_category": top_cat[0] if top_cat else None,
        "top_spending_amount": round(top_cat[1], 2) if top_cat else 0.0,
    }


def update_session_upload_context(session_id: str, payload: dict[str, Any]) -> None:
    """Persist doc_info, identity_scope, and session-only transactions on ai_sessions."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE ai_sessions
            SET upload_scope_context = %s::jsonb,
                cached_context = NULL,
                context_built_at = NULL
            WHERE id = %s::uuid
            """,
            (json.dumps(payload, default=str), session_id),
        )
        conn.commit()
    except Exception as e:
        _log.warning("[ai_context] update_session_upload_context failed: %s", e)
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


def save_upload_scope_context(session_id: str, identity_scope: dict) -> None:
    """Backward-compatible wrapper — prefer update_session_upload_context."""
    update_session_upload_context(session_id, {"identity_scope": identity_scope})


def load_upload_scope_context(session_id: str) -> dict | None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT upload_scope_context FROM ai_sessions WHERE id = %s::uuid",
            (session_id,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        val = row[0]
        return val if isinstance(val, dict) else json.loads(val)
    except Exception:
        return None
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


def merge_session_upload_into_packet(packet: dict[str, Any], session_id: str | None) -> dict[str, Any]:
    """Inject session-only upload data from ai_sessions.upload_scope_context."""
    if not session_id:
        return packet
    ctx = load_upload_scope_context(session_id)
    if not ctx:
        return packet

    txns = ctx.get("transactions") or []
    identity = ctx.get("identity_scope") or {}
    scope = identity.get("scope", "no_upload")
    doc_info = ctx.get("doc_info") or {}

    identity_reason = identity.get("reason")
    packet["session_upload"] = {
        "doc_info": doc_info,
        "identity_scope": scope,
        "identity_reason": identity_reason,
        "transaction_count": len(txns),
        "health_preview": ctx.get("health_preview"),
        "extracted_at": ctx.get("extracted_at"),
        "transactions": txns[:100],
        "instruction": (
            "Use ONLY this block for questions about the file just uploaded in chat. "
            "Do not describe linked_accounts or older uploaded_documents as this upload."
        ),
    }

    # Prevent the model from conflating past DB uploads (e.g. HDFC) with the current session file.
    packet["uploaded_documents"] = [
        {
            "file": "current_chat_session_upload",
            "type": doc_info.get("document_type"),
            "institution": doc_info.get("institution_name"),
            "account_holder_name": doc_info.get("account_holder_name"),
            "is_current_session": True,
            "transaction_count": len(txns),
        }
    ]

    if txns:
        session_txn_view = [
            {
                "merchant": t.get("description", "")[:80],
                "category": t.get("category", "other"),
                "amount": t.get("amount", 0),
                "date": t.get("date"),
                "type": t.get("type", "debit"),
                "source": "session_upload",
            }
            for t in txns[:50]
        ]
        ledger_authority = (packet.get("data_authority") or "") in (
            "ledger_month",
            "ledger_90d",
            "latest_ledger_upload",
        )
        has_ledger_txns = bool(packet.get("recent_transactions")) and ledger_authority

        if scope == "unlinked_foreign" and not has_ledger_txns:
            packet["recent_transactions"] = session_txn_view
            packet["active_emis"] = []
            packet["subscriptions"] = _recurring_services_from_transactions(txns)
        elif scope == "unlinked_foreign" and has_ledger_txns:
            packet["session_upload"]["transactions"] = session_txn_view
        else:
            packet["recent_transactions"] = session_txn_view + (packet.get("recent_transactions") or [])
            packet["recent_transactions"] = packet["recent_transactions"][:50]

        hp = ctx.get("health_preview") or {}
        if hp and scope in ("unlinked_foreign", "unlinked_same_bank") and not has_ledger_txns:
            packet["monthly_summary"] = {
                "expense": hp.get("total_debits", 0),
                "income": hp.get("total_credits", 0),
                "savings": hp.get("net", 0),
                "savings_rate": hp.get("savings_rate_pct", 0),
                "period_label": doc_info.get("statement_period") or packet.get("period_label"),
                "source": "session_upload",
                "transaction_count": len(txns),
            }
            packet["has_data"] = True
            packet["data_authority"] = "session_upload"
        elif hp and scope in ("unlinked_foreign", "unlinked_same_bank") and has_ledger_txns:
            packet["session_upload"]["monthly_summary"] = {
                "expense": hp.get("total_debits", 0),
                "income": hp.get("total_credits", 0),
                "savings": hp.get("net", 0),
                "savings_rate": hp.get("savings_rate_pct", 0),
                "period_label": doc_info.get("statement_period"),
                "source": "session_upload",
                "transaction_count": len(txns),
            }

        if scope in ("unlinked_foreign", "unlinked_same_bank", "linked_full"):
            upload_subs = _recurring_services_from_transactions(txns)
            if scope == "unlinked_foreign" and has_ledger_txns:
                packet["session_upload"]["subscriptions"] = upload_subs
            else:
                packet["subscriptions"] = upload_subs or packet.get("subscriptions") or []

    return packet


def get_or_build_context_packet(
    user_id: int,
    session_id: str | None,
    dashboard_scope: str = "merged",
    context_month: int | None = None,
    context_year: int | None = None,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    """Return cached context when fresh; otherwise build and persist to ai_sessions."""
    mode = normalize_dashboard_mode(dashboard_scope)
    now = datetime.now()
    month = int(context_month or now.month)
    year = int(context_year or now.year)

    if session_id and not force_rebuild:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT cached_context, context_built_at,
                       cache_dashboard_scope, cache_context_month, cache_context_year
                FROM ai_sessions
                WHERE id = %s::uuid AND user_id = %s
                """,
                (session_id, user_id),
            )
            row = cur.fetchone()
            if row and row[0] and row[1]:
                built_at = row[1]
                if built_at.tzinfo is None:
                    built_at = built_at.replace(tzinfo=timezone.utc)
                age = datetime.now(timezone.utc) - built_at.astimezone(timezone.utc)
                scope_ok = (row[2] or "merged") == mode
                month_ok = int(row[3] or 0) == month
                year_ok = int(row[4] or 0) == year
                if age < timedelta(minutes=_CACHE_TTL_MINUTES) and scope_ok and month_ok and year_ok:
                    cached = row[0]
                    packet = cached if isinstance(cached, dict) else json.loads(cached)
                    packet["user_id"] = user_id
                    return merge_session_upload_into_packet(packet, session_id)
        except Exception as e:
            _log.warning("[ai_context] cache read failed: %s", e)
        finally:
            try:
                cur.close()
            except Exception:
                pass
            conn.close()

    packet = build_context_packet(
        user_id,
        session_id=session_id,
        dashboard_scope=mode,
        context_month=month,
        context_year=year,
    )

    if session_id:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE ai_sessions
                SET cached_context = %s::jsonb,
                    context_built_at = NOW(),
                    cache_dashboard_scope = %s,
                    cache_context_month = %s,
                    cache_context_year = %s
                WHERE id = %s::uuid AND user_id = %s
                """,
                (
                    json.dumps(packet, default=str),
                    mode,
                    month,
                    year,
                    session_id,
                    user_id,
                ),
            )
            conn.commit()
        except Exception as e:
            _log.warning("[ai_context] cache write failed: %s", e)
        finally:
            try:
                cur.close()
            except Exception:
                pass
            conn.close()

    return merge_session_upload_into_packet(packet, session_id)


def _txn_dict_from_row(row: tuple) -> dict[str, Any]:
    return {
        "merchant": row[0] or "Unknown",
        "category": row[1],
        "amount": float(row[2] or 0),
        "date": str(row[3]),
        "type": (row[4] or "DEBIT").upper(),
        "source": row[5] or "linked_bank",
    }


def _fetch_scoped_transactions(
    cur: Any,
    user_id: int,
    scope_sql: str,
    *,
    month: int | None = None,
    year: int | None = None,
    days: int | None = None,
    connected_source_id: int | None = None,
    uploaded_document_id: int | None = None,
    limit: int = 80,
) -> list[dict[str, Any]]:
    clauses = ["t.user_id = %s", f"({scope_sql})"]
    params: list[Any] = [user_id]

    if connected_source_id is not None:
        clauses.append("t.connected_source_id = %s")
        params.append(connected_source_id)
    if uploaded_document_id is not None:
        clauses.append("t.uploaded_document_id = %s")
        params.append(uploaded_document_id)
    if month is not None and year is not None:
        clauses.append("EXTRACT(MONTH FROM t.transaction_date)::int = %s")
        clauses.append("EXTRACT(YEAR FROM t.transaction_date)::int = %s")
        params.extend([month, year])
    elif days is not None:
        clauses.append("t.transaction_date >= (CURRENT_DATE - (%s || ' days')::interval)")
        params.append(int(days))

    params.append(limit)
    cur.execute(
        f"""
        SELECT COALESCE(NULLIF(TRIM(merchant), ''), NULLIF(TRIM(description), ''), 'Unknown'),
               category, amount, transaction_date, type,
               'linked_bank'
        FROM transactions t
        WHERE {' AND '.join(clauses)}
        ORDER BY transaction_date DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return [_txn_dict_from_row(r) for r in cur.fetchall()]


def _summary_from_transactions(
    txns: list[dict[str, Any]],
    *,
    period_label: str,
    period_key: str,
    source: str,
) -> dict[str, Any]:
    total_income = 0.0
    total_expense = 0.0
    categories: dict[str, float] = {}
    for t in txns:
        amt = float(t.get("amount") or 0)
        typ = str(t.get("type") or "DEBIT").upper()
        if typ == "CREDIT":
            total_income += amt
        else:
            total_expense += amt
            cat = str(t.get("category") or "Other")
            categories[cat] = categories.get(cat, 0.0) + amt
    savings = total_income - total_expense
    savings_rate = round(savings / total_income * 100, 2) if total_income > 0 else 0.0
    return {
        "income": round(total_income, 2),
        "expense": round(total_expense, 2),
        "savings": round(savings, 2),
        "savings_rate": savings_rate,
        "categories": categories,
        "period": period_key,
        "period_label": period_label,
        "source": source,
        "transaction_count": len(txns),
    }


def _recurring_services_from_transactions(txns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for t in txns:
        if str(t.get("type", "DEBIT")).upper() != "DEBIT":
            continue
        label = str(t.get("merchant") or "")
        low = label.lower()
        if not any(h in low for h in _RECURRING_MERCHANT_HINTS):
            continue
        key = low[:48]
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "service": label[:80],
            "amount": float(t.get("amount") or 0),
            "billing_date": t.get("date"),
            "status": "from_statement",
        })
    return out[:10]


def _fetch_latest_ledger_upload(cur: Any, user_id: int) -> dict[str, Any] | None:
    try:
        cur.execute(
            """
            SELECT ud.id, ud.file_name, ud.uploaded_at, ud.connected_source_id,
                   COALESCE(ud.rows_imported, 0), cs.institution_name, cs.source_type
            FROM uploaded_documents ud
            LEFT JOIN connected_sources cs ON cs.id = ud.connected_source_id
            WHERE ud.user_id = %s
            ORDER BY ud.uploaded_at DESC NULLS LAST, ud.id DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        doc_id = int(row[0])
        holder: str | None = None
        try:
            cur.execute(
                """
                SELECT raw_extracted_text
                FROM extraction_results
                WHERE uploaded_document_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (doc_id,),
            )
            er = cur.fetchone()
            if er and er[0]:
                holder = detect_holder_in_text(str(er[0]))
        except Exception:
            pass
        return {
            "document_id": doc_id,
            "filename": row[1],
            "uploaded_at": str(row[2]) if row[2] else None,
            "connected_source_id": int(row[3]) if row[3] is not None else None,
            "rows_imported": int(row[4] or 0),
            "institution": row[5],
            "source_type": row[6],
            "account_holder_name": holder,
        }
    except Exception as e:
        _rollback_conn(cur.connection)
        _log.warning("[ai_context] latest_ledger_upload fetch error: %s", e)
        return None


def build_context_prompt_rules(context: dict[str, Any]) -> str:
    """Grounding rules appended to the chat system prompt."""
    user_name = (context.get("user") or {}).get("name") or context.get("user_name") or "there"
    has_data = bool(context.get("has_data"))
    authority = context.get("data_authority") or "none"
    latest = context.get("latest_ledger_upload") or {}
    holder = latest.get("account_holder_name")
    lines = [
        "═══ CONTEXT GROUNDING (MANDATORY) ═══",
        f"1. Greet the logged-in user as: {user_name} (from their account — never invent another name).",
        "2. Use ONLY numbers and merchants listed in the CONTEXT PACKET in the user message.",
        "3. NEVER cite profile monthly_income unless the packet says no ledger data exists.",
        "4. Do NOT mention rent, salary, Spotify, or any merchant not present in recent_transactions.",
    ]
    if not has_data:
        lines.append(
            "5. This user has no scoped ledger rows yet — say so and suggest uploading via Connected Accounts."
        )
    else:
        lines.append(f"5. Data authority: {authority} — prefer latest_ledger_upload / session_upload over stale profile.")
    if holder and holder.lower() != str(user_name).lower():
        lines.append(
            f"6. Latest statement holder on file: {holder}. "
            f"Describe that statement's spends; do not claim they are {user_name}'s salary/profile income."
        )
    return "\n".join(lines)


def build_context_packet(
    user_id: int,
    session_id: str | None = None,
    dashboard_scope: str = "merged",
    context_month: int | None = None,
    context_year: int | None = None,
) -> dict[str, Any]:
    """
    Fetch scoped, month-aware data for the AI chatbot.

    dashboard_scope: bank_only | credit_card_only | merged
    context_month/year: month being viewed on dashboard (defaults to current)
    """
    now = datetime.now()
    month = int(context_month or now.month)
    year = int(context_year or now.year)
    mode = normalize_dashboard_mode(dashboard_scope)
    scope = transaction_scope_sql("t", mode)
    last_day = calendar.monthrange(year, month)[1]
    period_label = f"{calendar.month_name[month]} {year}"

    conn = get_connection()
    cur = None
    user_data: dict[str, Any] = {}
    planning_snapshot: dict[str, Any] = {}
    has_data = False
    data_authority = "none"
    recent_txns: list[dict] = []
    monthly_summary: dict = {}
    latest_ledger_upload = None
    connected_sources: list[dict] = []
    linked_accounts: list[dict] = []
    subscriptions: list[dict] = []
    active_emis: list[dict] = []
    uploaded_docs: list[dict] = []
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, name, email, monthly_income, savings_goal,
                       COALESCE(risk_tolerance, 'moderate') AS risk_tolerance
                FROM users WHERE id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                profile_income = float(row[3] or 0)
                user_data = {
                    "name": (row[1] or "").strip() or "there",
                    "profile_monthly_income": profile_income if profile_income > 0 else None,
                    "savings_goal": float(row[4] or 0),
                    "risk_tolerance": row[5],
                }
        except Exception as e:
            _rollback_conn(conn)
            _log.warning("[ai_context] user fetch error: %s", e)

        connected_sources = _fetch_connected_sources(cur, user_id)
        linked_accounts = [
            {
                "bank": s["institution_name"],
                "source_type": s.get("source_type"),
                "status": s.get("status", "active"),
            }
            for s in connected_sources
        ]

        latest_ledger_upload = _fetch_latest_ledger_upload(cur, user_id)

        try:
            primary_txns: list[dict] = []
            if latest_ledger_upload and int(latest_ledger_upload.get("rows_imported") or 0) > 0:
                src_id = latest_ledger_upload.get("connected_source_id")
                doc_id = latest_ledger_upload.get("document_id")
                if src_id:
                    primary_txns = _fetch_scoped_transactions(
                        cur,
                        user_id,
                        scope,
                        days=_LEDGER_LOOKBACK_DAYS,
                        connected_source_id=src_id,
                        limit=80,
                    )
                if not primary_txns and doc_id:
                    primary_txns = _fetch_scoped_transactions(
                        cur,
                        user_id,
                        scope,
                        days=_LEDGER_LOOKBACK_DAYS,
                        uploaded_document_id=doc_id,
                        limit=80,
                    )
                if primary_txns:
                    data_authority = "latest_ledger_upload"
                    inst = latest_ledger_upload.get("institution") or "linked account"
                    recent_txns = primary_txns[:50]
                    monthly_summary = _summary_from_transactions(
                        primary_txns,
                        period_label=f"Latest upload ({inst})",
                        period_key="latest_upload",
                        source="latest_ledger_upload",
                    )

            if not recent_txns:
                month_txns = _fetch_scoped_transactions(
                    cur, user_id, scope, month=month, year=year, limit=50
                )
                if month_txns:
                    recent_txns = month_txns
                    data_authority = "ledger_month"
                    monthly_summary = _summary_from_transactions(
                        month_txns,
                        period_label=period_label,
                        period_key=f"{year}-{month:02d}",
                        source="ledger_month",
                    )
                else:
                    rolling_txns = _fetch_scoped_transactions(
                        cur, user_id, scope, days=_LEDGER_LOOKBACK_DAYS, limit=80
                    )
                    if rolling_txns:
                        recent_txns = rolling_txns[:50]
                        data_authority = "ledger_90d"
                        monthly_summary = _summary_from_transactions(
                            rolling_txns,
                            period_label=f"Last {_LEDGER_LOOKBACK_DAYS} days",
                            period_key="rolling_90d",
                            source="ledger_90d",
                        )
        except Exception as e:
            _rollback_conn(conn)
            _log.warning("[ai_context] transactions fetch error: %s", e)

        has_data = len(recent_txns) > 0

        if has_data:
            subscriptions = _recurring_services_from_transactions(recent_txns)
        else:
            try:
                cur.execute(
                    """
                    SELECT
                        COALESCE(merchant, 'Unknown') AS lender,
                        COALESCE(detected_amount, 0) AS emi_amount,
                        payment_date,
                        COALESCE(months_detected, 0) AS months_remaining
                    FROM emi_records
                    WHERE user_id = %s AND is_active IS TRUE
                    ORDER BY payment_date ASC NULLS LAST
                    LIMIT 10
                    """,
                    (user_id,),
                )
                for r in cur.fetchall():
                    active_emis.append({
                        "lender": r[0],
                        "amount": float(r[1] or 0),
                        "next_due": str(r[2]) if r[2] else None,
                        "remaining_months": int(r[3] or 0),
                    })
            except Exception as e:
                _rollback_conn(conn)
                _log.warning("[ai_context] emi_records fetch error: %s", e)

            try:
                cur.execute(
                    """
                    SELECT
                        COALESCE(merchant, 'Unknown') AS service,
                        COALESCE(NULLIF(monthly_cost, 0), amount, 0)::double precision AS amount,
                        COALESCE(last_charged, first_charged) AS billing_date,
                        COALESCE(status, 'active') AS status
                    FROM subscriptions
                    WHERE user_id = %s
                      AND (status IS NULL OR LOWER(status) NOT IN ('cancelled', 'pending_cancel'))
                    ORDER BY 3 ASC NULLS LAST
                    LIMIT 10
                    """,
                    (user_id,),
                )
                for r in cur.fetchall():
                    subscriptions.append({
                        "service": r[0],
                        "amount": float(r[1] or 0),
                        "billing_date": str(r[2]) if r[2] else None,
                        "status": r[3],
                    })
            except Exception as e:
                _rollback_conn(conn)
                _log.warning("[ai_context] subscriptions fetch error: %s", e)

        if latest_ledger_upload:
            uploaded_docs.append({
                "file": latest_ledger_upload.get("filename"),
                "institution": latest_ledger_upload.get("institution"),
                "type": latest_ledger_upload.get("source_type"),
                "is_current_ledger": True,
                "account_holder_name": latest_ledger_upload.get("account_holder_name"),
                "rows_imported": latest_ledger_upload.get("rows_imported"),
                "uploaded_at": latest_ledger_upload.get("uploaded_at"),
            })
        if session_id:
            try:
                cur.execute(
                    """
                    SELECT file_name, document_type, institution,
                           is_linked_account, extracted_json
                    FROM document_uploads
                    WHERE user_id = %s AND session_id = %s::uuid
                      AND expires_at > NOW()
                    """,
                    (user_id, session_id),
                )
                for r in cur.fetchall():
                    try:
                        extracted = r[4] if isinstance(r[4], dict) else (
                            json.loads(r[4]) if r[4] else {}
                        )
                    except Exception:
                        extracted = {}
                    uploaded_docs.append({
                        "file": r[0],
                        "type": r[1],
                        "institution": r[2],
                        "is_linked": bool(r[3]),
                        "data": extracted,
                    })
            except Exception as e:
                _rollback_conn(conn)
                _log.warning("[ai_context] document_uploads fetch error: %s", e)

        try:
            from services.financial_behavior import fetch_planning_snapshot

            income_basis = float((monthly_summary or {}).get("income") or 0)
            if income_basis <= 0:
                income_basis = float(user_data.get("profile_monthly_income") or 0)
            planning_snapshot = fetch_planning_snapshot(cur, user_id, income_basis=income_basis)
        except Exception as e:
            _rollback_conn(conn)
            _log.warning("[ai_context] planning_snapshot fetch error: %s", e)

        _log.info(
            "[ai_context] build user_id=%s name=%s has_data=%s authority=%s txn_count=%s upload=%s",
            user_id,
            user_data.get("name"),
            has_data,
            data_authority,
            len(recent_txns),
            (latest_ledger_upload or {}).get("filename"),
        )

    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()

    user_name = (user_data.get("name") or "there").strip()
    return {
        "user_id": user_id,
        "user_name": user_name,
        "has_data": has_data,
        "planning_snapshot": planning_snapshot,
        "data_authority": data_authority,
        "user": user_data,
        "linked_accounts": linked_accounts,
        "latest_ledger_upload": latest_ledger_upload,
        "monthly_summary": monthly_summary,
        "recent_transactions": recent_txns,
        "active_emis": active_emis,
        "subscriptions": subscriptions,
        "uploaded_documents": uploaded_docs,
        "dashboard_scope": mode,
        "context_month": month,
        "context_year": year,
        "period_label": period_label,
        "grounding_note": (
            "All figures below are from the user's scoped ledger/upload — "
            "do not use profile_monthly_income or demo personas."
            if has_data
            else "No scoped ledger rows — do not invent amounts or merchants."
        ),
        "app_features": [
            {"name": "EMI Tracker", "route": "/emi-tracker", "tab": "emi",
             "description": "Track all EMIs, due dates, lenders"},
            {"name": "Subscriptions AI", "route": "/subscriptions-ai", "tab": "subscriptions",
             "description": "Manage recurring subscriptions"},
            {"name": "FraudShield", "route": "/fraud-shield", "tab": "fraud",
             "description": "Detect suspicious transactions"},
            {"name": "Transactions", "route": "/transactions", "tab": "transactions",
             "description": "Full transaction history"},
            {"name": "Trip Planner", "route": "/trip-planner", "tab": "trip-planner",
             "description": "Plan trips within your budget"},
            {"name": "AI Insights", "route": "/insights", "tab": "insights",
             "description": "Full financial analysis"},
        ],
    }
