"""Dark pattern and rupee-trap detection routes."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_db
from services.dashboard_scope import resolve_scope_mode, transaction_scope_sql
from services.openai_service import call_gpt

router = APIRouter(prefix="/dark-patterns", tags=["Dark Patterns"])


def _severity(label: str) -> str:
    if label in ("DUPLICATE_CHARGE", "ESCALATING", "EK_RUPEE_TRAP"):
        return "CRITICAL"
    if label in ("FREE_TRIAL_TRAP", "PRICE_INCREASE"):
        return "HIGH"
    if label == "ZOMBIE":
        return "MEDIUM"
    return "LOW"


def _to_dt(d: date, t: Any) -> datetime:
    if isinstance(t, datetime):
        return t
    return datetime.combine(d, t)


def _fetch_transactions(
    conn, user_id: int, months: int = 18, scope: str | None = None
) -> list[dict[str, Any]]:
    cur = conn.cursor()
    try:
        mode = resolve_scope_mode(cur, user_id, scope)
        scope_sql = transaction_scope_sql("t", mode)
        cur.execute(
            f"""
            SELECT t.id, t.transaction_date, t.transaction_time, t.amount::float, COALESCE(t.type, ''),
                   COALESCE(t.merchant, ''), COALESCE(t.category, ''), COALESCE(t.description, '')
            FROM transactions t
            WHERE t.user_id = %s
              AND t.transaction_date >= (CURRENT_DATE - (%s || ' months')::interval)
              AND ({scope_sql})
            ORDER BY t.transaction_date, t.transaction_time;
            """,
            (user_id, months),
        )
        rows = cur.fetchall()
    finally:
        cur.close()

    txns = []
    for rid, d, tm, amt, tx_type, merchant, category, desc in rows:
        txns.append(
            {
                "id": int(rid),
                "date": d,
                "time": tm,
                "dt": _to_dt(d, tm),
                "amount": float(amt or 0),
                "type": (tx_type or "").strip().upper(),
                "merchant": merchant.strip(),
                "category": category.strip(),
                "description": desc.strip(),
            }
        )
    return txns


def _group_by_merchant(txns: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in txns:
        if t["type"] == "DEBIT" and t["merchant"]:
            grouped[t["merchant"]].append(t)
    return grouped


def detect_free_trial_traps(grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for merchant, items in grouped.items():
        low_m = merchant.lower()
        if not any(
            k in low_m
            for k in (
                "cloud",
                "vpn",
                "secure",
                "pro",
                "trial",
                "app",
                "apple",
                "bill",
                "micro auth",
                "hotstar",
                "youtube",
                "netflix",
                "prime",
                "openai",
                "spotify",
                "google play",
            )
        ):
            continue
        items = sorted(items, key=lambda x: x["dt"])
        for i, tx in enumerate(items):
            if 1 <= tx["amount"] <= 5:
                for nxt in items[i + 1 :]:
                    gap = (nxt["date"] - tx["date"]).days
                    if 15 <= gap <= 45 and nxt["amount"] >= 199:
                        out.append(
                            {
                                "merchant": merchant,
                                "pattern_type": "FREE_TRIAL_TRAP",
                                "description": (
                                    f"Small trial charge {tx['amount']:.0f} on {tx['date']} "
                                    f"was followed by {nxt['amount']:.0f} within {gap} days."
                                ),
                                "amount_involved": round(nxt["amount"], 2),
                                "potential_loss": round(nxt["amount"], 2),
                                "detected_date": date.today().isoformat(),
                                "severity": _severity("FREE_TRIAL_TRAP"),
                                "action": (
                                    f"Cancel auto-renew before next cycle to avoid {nxt['amount']:.0f} charge."
                                ),
                                "deadline": nxt["date"].isoformat(),
                                "evidence": {
                                    "initial_charge": {
                                        "transaction_id": tx["id"],
                                        "date": tx["date"].isoformat(),
                                        "amount": tx["amount"],
                                    },
                                    "followup_charge": {
                                        "transaction_id": nxt["id"],
                                        "date": nxt["date"].isoformat(),
                                        "amount": nxt["amount"],
                                    },
                                },
                            }
                        )
                        break
    return out


def detect_price_increases(grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for merchant, items in grouped.items():
        low_m = merchant.lower()
        if not any(k in low_m for k in ("app", "premium", "plus", "fit", "plan", "vpn")):
            continue
        if len(items) < 3:
            continue
        monthly = sorted(items, key=lambda x: x["dt"])
        recurring = [x for x in monthly if 99 <= x["amount"] <= 5000]
        if len(recurring) < 3:
            continue
        amounts = [x["amount"] for x in recurring[-4:]]
        if len(amounts) >= 3 and all(amounts[i] <= amounts[i + 1] for i in range(len(amounts) - 1)):
            increase_pct = ((amounts[-1] - amounts[0]) / max(amounts[0], 1)) * 100
            if increase_pct > 10 and amounts[-1] <= 3000:
                out.append(
                    {
                        "merchant": merchant,
                        "pattern_type": "PRICE_INCREASE",
                        "description": (
                            f"Recurring charge increased from {amounts[0]:.0f} to {amounts[-1]:.0f} "
                            f"({increase_pct:.0f}% increase)."
                        ),
                        "amount_involved": round(amounts[-1], 2),
                        "potential_loss": round(amounts[-1] - amounts[0], 2),
                        "detected_date": date.today().isoformat(),
                        "severity": _severity("PRICE_INCREASE"),
                        "original_price": round(amounts[0], 2),
                        "current_price": round(amounts[-1], 2),
                        "increase_pct": round(increase_pct, 1),
                        "action": "Contact support for legacy pricing or cancel the plan.",
                        "evidence": {
                            "timeline": [
                                {
                                    "transaction_id": x["id"],
                                    "date": x["date"].isoformat(),
                                    "amount": x["amount"],
                                }
                                for x in recurring[-4:]
                            ]
                        },
                    }
                )
    return out


def detect_duplicates(grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for merchant, items in grouped.items():
        items = sorted(items, key=lambda x: x["dt"])
        for i in range(1, len(items)):
            a, b = items[i - 1], items[i]
            if abs(a["amount"] - b["amount"]) < 0.01:
                mins = int((b["dt"] - a["dt"]).total_seconds() / 60)
                if 0 <= mins <= 60:
                    out.append(
                        {
                            "merchant": merchant,
                            "pattern_type": "DUPLICATE_CHARGE",
                            "description": (
                                f"Same amount {a['amount']:.0f} charged twice within {mins} minutes."
                            ),
                            "amount_involved": round(a["amount"], 2),
                            "potential_loss": round(a["amount"], 2),
                            "refund_amount": round(a["amount"], 2),
                            "detected_date": date.today().isoformat(),
                            "severity": _severity("DUPLICATE_CHARGE"),
                            "action": "Raise a duplicate-charge dispute with the merchant or bank immediately.",
                            "evidence": {
                                "charge_1": {
                                    "transaction_id": a["id"],
                                    "date": a["date"].isoformat(),
                                    "time": str(a["time"]),
                                    "amount": a["amount"],
                                },
                                "charge_2": {
                                    "transaction_id": b["id"],
                                    "date": b["date"].isoformat(),
                                    "time": str(b["time"]),
                                    "amount": b["amount"],
                                },
                            },
                        }
                    )
    return out


def detect_escalating_amounts(grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for merchant, items in grouped.items():
        low_m = merchant.lower()
        if not any(k in low_m for k in ("trading", "unknown", "prize", "kyc", "verify")):
            continue
        items = sorted(items, key=lambda x: x["dt"])
        amounts = [x["amount"] for x in items]
        if len(amounts) < 3:
            continue
        if min(amounts) <= 5 and max(amounts) >= 1000:
            rising = 0
            for i in range(1, len(amounts)):
                if amounts[i] > amounts[i - 1]:
                    rising += 1
            if rising >= 2:
                out.append(
                    {
                        "merchant": merchant,
                        "pattern_type": "ESCALATING",
                        "description": "Amounts escalated from small verification charges to high-value debits.",
                        "amount_involved": round(max(amounts), 2),
                        "potential_loss": round(sum(amounts), 2),
                        "detected_date": date.today().isoformat(),
                        "severity": _severity("ESCALATING"),
                        "action": "Block merchant and payment method immediately; report to cybercrime.",
                        "evidence": {
                            "sequence": [
                                {"transaction_id": x["id"], "date": x["date"].isoformat(), "amount": x["amount"]}
                                for x in items[-6:]
                            ]
                        },
                    }
                )
    return out


def detect_micro_auth_traps(grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Flag ₹1–₹5 verification debits from subscription / app-store merchants."""
    out: list[dict[str, Any]] = []
    markers = (
        "micro auth",
        "apple.com",
        ".com/bill",
        "google play",
        "play store",
        "hotstar",
        "youtube",
        "netflix",
        "prime",
        "openai",
        "spotify",
        "verify",
    )
    for merchant, items in grouped.items():
        low_m = merchant.lower()
        if not any(k in low_m for k in markers):
            continue
        items = sorted(items, key=lambda x: x["dt"])
        for tx in items:
            if tx["type"] != "DEBIT" or not (0.5 <= tx["amount"] <= 5):
                continue
            follow = next(
                (x for x in items if x["date"] > tx["date"] and x["amount"] >= 99),
                None,
            )
            est = float(follow["amount"]) if follow else 499.0
            out.append(
                {
                    "merchant": merchant,
                    "pattern_type": "EK_RUPEE_TRAP",
                    "description": (
                        f"Micro-authorization ₹{tx['amount']:.0f} on {tx['date']} — "
                        f"typical free-trial or card-verify pattern. Watch for ~₹{est:.0f} follow-up."
                    ),
                    "amount_involved": round(est, 2),
                    "potential_loss": round(est, 2),
                    "detected_date": tx["date"].isoformat(),
                    "severity": _severity("EK_RUPEE_TRAP"),
                    "action": "Cancel auto-renew in the merchant app before the predicted charge date.",
                    "evidence": {
                        "micro_charge": {
                            "transaction_id": tx["id"],
                            "date": tx["date"].isoformat(),
                            "amount": tx["amount"],
                        },
                        "estimated_followup": est,
                    },
                }
            )
            break
    return out


def detect_zombies(grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    today = date.today()
    watchlist = {"magztergold", "linkedin premium", "adobe creative", "zee5 premium", "cultfit", "audible india"}
    for merchant, items in grouped.items():
        if merchant.lower() not in watchlist:
            continue
        recurring = [x for x in items if 99 <= x["amount"] <= 5000]
        if len(recurring) < 4:
            continue
        recurring = sorted(recurring, key=lambda x: x["dt"])
        last_charge = recurring[-1]["date"]
        prior_nonrecent = [x for x in recurring[:-1] if (today - x["date"]).days > 120]
        if prior_nonrecent and (today - last_charge).days <= 40:
            out.append(
                {
                    "merchant": merchant,
                    "pattern_type": "ZOMBIE",
                    "description": "Recurring charge appears active while meaningful usage is stale.",
                    "amount_involved": round(recurring[-1]["amount"], 2),
                    "potential_loss": round(recurring[-1]["amount"], 2),
                    "detected_date": date.today().isoformat(),
                    "severity": _severity("ZOMBIE"),
                    "action": "Audit the subscription and cancel if no active use in the last 3 months.",
                    "evidence": {
                        "last_charge": {
                            "transaction_id": recurring[-1]["id"],
                            "date": recurring[-1]["date"].isoformat(),
                            "amount": recurring[-1]["amount"],
                        }
                    },
                }
            )
    return out


def detect_rupee_traps(txns: list[dict[str, Any]]) -> dict[str, Any]:
    suspicious_keywords = ("kyc", "verify", "update", "bank", "refund", "prize", "lottery", "claim")
    by_merchant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in txns:
        if t["type"] == "DEBIT" and t["merchant"]:
            by_merchant[t["merchant"]].append(t)

    traps: list[dict[str, Any]] = []
    escalations = 0
    total_lost = 0.0

    for merchant, items in by_merchant.items():
        items = sorted(items, key=lambda x: x["dt"])
        for idx, tx in enumerate(items):
            amt = tx["amount"]
            if not (1 <= amt <= 10):
                continue
            prior = items[:idx]
            new_payee = len(prior) == 0
            unusual_hour = tx["dt"].hour >= 22 or tx["dt"].hour <= 6
            low_m = merchant.lower()
            suspicious_id = any(k in low_m for k in suspicious_keywords) or ("@" in low_m and "-" in low_m)
            desc_hit = any(k in (tx["description"] or "").lower() for k in ("verify", "test", "confirm"))
            subscription_micro = any(
                k in low_m
                for k in ("micro auth", "apple.com", ".com/bill", "google play", "play store", "hotstar", "youtube")
            )

            risk = 0
            if new_payee:
                risk += 40
            if unusual_hour:
                risk += 30
            if suspicious_id:
                risk += 40
            if desc_hit:
                risk += 20
            if subscription_micro:
                risk = max(risk, 55)

            next_7 = [
                x for x in items[idx + 1 :] if 0 < (x["date"] - tx["date"]).days <= 7 and 50 <= x["amount"] <= 500
            ]
            next_30 = [x for x in items[idx + 1 :] if 0 < (x["date"] - tx["date"]).days <= 30 and x["amount"] >= 1000]
            escalation_detected = len(next_7) > 0 and len(next_30) > 0
            if escalation_detected:
                risk = 95
                escalations += 1
                seq = [tx] + [x for x in items[idx + 1 :] if (x["date"] - tx["date"]).days <= 30]
                lost = round(sum(x["amount"] for x in seq), 2)
                total_lost += lost
                warning = f"Confirmed escalation pattern. Total loss linked to this trap: {lost:,.0f}."
                timeline = [round(x["amount"], 2) for x in seq]
            else:
                lost = 0.0
                warning = "Suspicious low-value verification payment pattern detected."
                timeline = [round(tx["amount"], 2)]

            explanation_prompt = f"""
Merchant: {merchant}
Initial amount: {tx['amount']}
Initial datetime: {tx['dt']}
Risk score: {risk}
Escalation detected: {escalation_detected}
Escalation timeline amounts: {timeline}
Write 2 concise English warning sentences with actionable advice.
"""
            explain = call_gpt(
                system_prompt="You are a financial fraud safety assistant. Respond in clear English only.",
                user_prompt=explanation_prompt.strip(),
                max_tokens=120,
                json_mode=False,
            )
            english_explanation = "This transaction pattern looks risky. Do not send verification payments to unknown UPI IDs."
            if isinstance(explain, str) and explain.strip() and not explain.strip().startswith("AI insights unavailable"):
                english_explanation = explain.strip()

            traps.append(
                {
                    "merchant": merchant,
                    "initial_amount": round(tx["amount"], 2),
                    "initial_date": tx["date"].isoformat(),
                    "initial_time": str(tx["time"]),
                    "risk_score": int(min(100, risk)),
                    "escalation_detected": escalation_detected,
                    "escalation_amounts": timeline,
                    "total_lost": lost,
                    "warning": warning,
                    "english_explanation": english_explanation,
                }
            )
            break

    traps.sort(key=lambda x: (x["risk_score"], x["total_lost"]), reverse=True)
    return {
        "rupee_traps_found": len(traps),
        "confirmed_escalations": escalations,
        "total_lost_to_escalation": round(total_lost, 2),
        "traps": traps,
    }


def _detect_patterns(conn, user_id: int, scope: str | None = None) -> dict[str, Any]:
    txns = _fetch_transactions(conn, user_id, scope=scope)
    grouped = _group_by_merchant(txns)

    patterns = (
        detect_micro_auth_traps(grouped)
        + detect_free_trial_traps(grouped)
        + detect_price_increases(grouped)
        + detect_duplicates(grouped)
        + detect_escalating_amounts(grouped)
        + detect_zombies(grouped)
    )

    # dedupe by merchant+pattern type with highest amount
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for p in patterns:
        key = (p["merchant"], p["pattern_type"])
        if key not in deduped or p["amount_involved"] > deduped[key]["amount_involved"]:
            deduped[key] = p
    patterns = list(deduped.values())
    patterns.sort(key=lambda x: (x["severity"], x["amount_involved"]), reverse=True)
    # Keep report concise and actionable.
    patterns = patterns[:12]
    for idx, pattern in enumerate(patterns, start=1):
        pattern["id"] = idx

    total_risk = round(sum(float(p.get("potential_loss", 0) or 0) for p in patterns), 2)
    refunds = round(
        sum(float(p.get("refund_amount", p.get("potential_loss", 0)) or 0) for p in patterns if p["pattern_type"] == "DUPLICATE_CHARGE"),
        2,
    )
    critical = sum(1 for p in patterns if p["severity"] == "CRITICAL")

    ai_prompt = f"""
Detected dark patterns for user {user_id}:
{patterns}
Money at risk: {total_risk}
Potential refunds: {refunds}
Write concise advice in English only.
"""
    ai = call_gpt(
        system_prompt=(
            "You are SmartSpend consumer protection advisor. Explain dark-pattern charges in clear English. "
            "Be specific about amounts and dates. Plain text only, max 3 sentences."
        ),
        user_prompt=ai_prompt.strip(),
        max_tokens=180,
        json_mode=False,
    )
    raw = str(ai).strip() if isinstance(ai, str) else ""
    if raw.startswith("AI insights unavailable"):
        raw = ""
    ai_advice = raw or (
        "Review critical patterns first, dispute duplicate charges through your bank or UPI support, "
        "and disable risky auto-renewals to limit future leakage."
    )

    return {
        "total_dark_patterns": len(patterns),
        "critical_count": critical,
        "total_money_at_risk": total_risk,
        "potential_refunds": refunds,
        "patterns": patterns,
        "ai_advice": ai_advice,
    }


@router.get("/{user_id}")
def get_dark_patterns(
    user_id: int,
    scope: Optional[str] = Query(
        None,
        description="bank_only | credit_card_only | merged",
    ),
    conn=Depends(get_db),
):
    try:
        return _detect_patterns(conn, user_id, scope)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Dark pattern detection failed: {exc}") from exc


@router.get("/{user_id}/rupee-traps")
def get_rupee_trap_report(
    user_id: int,
    scope: Optional[str] = Query(
        None,
        description="bank_only | credit_card_only | merged",
    ),
    conn=Depends(get_db),
):
    try:
        txns = _fetch_transactions(conn, user_id, scope=scope)
        return detect_rupee_traps(txns)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Rupee trap detection failed: {exc}") from exc


@router.post("/{user_id}/scan")
def scan_dark_patterns(user_id: int, conn=Depends(get_db)):
    try:
        result = _detect_patterns(conn, user_id)
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM dark_patterns WHERE user_id = %s AND status <> 'RESOLVED';", (user_id,))
            for p in result["patterns"]:
                cur.execute(
                    """
                    INSERT INTO dark_patterns (
                        user_id, merchant, pattern_type, description, amount_involved, potential_loss,
                        detected_date, evidence, status, action_taken
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE, %s::jsonb, 'ACTIVE', %s);
                    """,
                    (
                        user_id,
                        p["merchant"],
                        p["pattern_type"],
                        p["description"],
                        p.get("amount_involved", 0),
                        p.get("potential_loss", 0),
                        json.dumps(p.get("evidence", {})),
                        p.get("action", ""),
                    ),
                )
        finally:
            cur.close()
        return {"patterns_found": result["total_dark_patterns"], "critical_count": result["critical_count"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Dark pattern scan failed: {exc}") from exc


@router.post("/{user_id}/{pattern_id}/resolve")
def resolve_dark_pattern(user_id: int, pattern_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE dark_patterns
            SET status = 'RESOLVED',
                action_taken = COALESCE(action_taken, '') || ' Marked resolved by user.'
            WHERE id = %s AND user_id = %s
            RETURNING id;
            """,
            (pattern_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return {
                "pattern_id": pattern_id,
                "status": "RESOLVED",
                "note": "No persisted row found. Run dark-pattern scan first to persist records.",
            }
        return {"pattern_id": pattern_id, "status": "RESOLVED"}
    finally:
        cur.close()
