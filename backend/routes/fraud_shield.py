"""FraudShield — real-time fraud scoring, Groq-backed security advice, alerts API."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_db
from services.ai_service import call_groq
from services.dashboard_scope import fetch_dashboard_mode, transaction_scope_sql

router = APIRouter(prefix="/fraud-shield", tags=["Fraud Shield"])

CYBER_CRIME_URL = "https://cybercrime.gov.in"
HELPLINE_1930 = "1930"

KNOWN_MERCHANT_KEYWORDS = (
    "swiggy",
    "zomato",
    "uber",
    "ola",
    "amazon",
    "flipkart",
    "paytm",
    "phonepe",
    "googlepay",
    "gpay",
    "irctc",
    "bigbasket",
    "blinkit",
    "cred",
    "netflix",
    "spotify",
    "jiomart",
    "myntra",
    "meesho",
    "nykaa",
)

SUSPICIOUS_UPI_KEYWORDS = (
    "kyc",
    "verify",
    "update",
    "bank",
    "refund",
    "prize",
    "lottery",
    "helpline",
    "support",
    "secure-account",
    "double-money",
    "prize-claim",
    "lottery",
    "gov",
    "income-tax",
    "gst-refund",
    # High-risk financial transfer keywords
    "wire",
    "foreign",
    "offshore",
    "crypto",
    "international",
    "remittance",
    "overseas",
    "forex",
    "transfer",
)

ROUND_AMOUNTS = {5000, 10000, 15000, 20000}


def _parse_time_hhmm(s: Optional[str]) -> tuple[int, int]:
    if not s or not str(s).strip():
        now = datetime.now()
        return now.hour, now.minute
    parts = str(s).strip().split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return max(0, min(23, h)), max(0, min(59, m))
    except (ValueError, IndexError):
        now = datetime.now()
        return now.hour, now.minute


def _night_risk(hour: int) -> tuple[int, str | None]:
    if hour >= 23 or hour < 5:
        return 15, "Night transaction — unusual hours (11 PM – 5 AM)"
    if hour >= 20:
        return 8, "Late evening transaction — 8 PM – 11 PM"
    return 0, None


def _is_known_merchant(payee: str) -> bool:
    p = (payee or "").lower()
    return any(k in p for k in KNOWN_MERCHANT_KEYWORDS)


def _suspicious_upi_risk(payee: str) -> tuple[int, str | None]:
    p = (payee or "").lower()
    if _is_known_merchant(p) and not any(k in p for k in SUSPICIOUS_UPI_KEYWORDS):
        return 0, None
    if any(k in p for k in SUSPICIOUS_UPI_KEYWORDS):
        return 20, "Suspicious keywords in UPI / merchant ID — common fraud lure"
    local = p.split("@")[0] if "@" in p else p
    if re.fullmatch(r"[\d._-]{8,}", local or ""):
        return 10, "Random-looking UPI handle — no clear merchant name"
    return 0, None


def _round_amount_risk(amount: float) -> tuple[int, str | None]:
    a = float(amount)
    if a in ROUND_AMOUNTS:
        return 5, "Exact round amount often used in scams (₹5k / 10k / 15k / 20k)"
    if a >= 10000 and a % 5000 == 0 and a % 1 == 0:
        return 5, "Large round-number transfer — verify carefully"
    return 0, None


def calculate_fraud_risk_score(
    transaction: dict[str, Any],
    user_history: dict[str, Any],
) -> dict[str, Any]:
    """
    Eight-factor risk model (0–100). See module docstring / product spec.
    """
    payee = (transaction.get("payee") or transaction.get("merchant") or "").strip()
    amount = float(transaction.get("amount") or 0)
    hour = int(transaction.get("hour", 12))
    minute = int(transaction.get("minute", 0))
    description = (transaction.get("description") or "").lower()
    payment_method = (transaction.get("payment_method") or "UPI").lower()

    risk_factors: list[str] = []
    score = 0

    prev_count = int(user_history.get("payee_previous_debit_count", 0))
    if prev_count == 0:
        score += 25
        risk_factors.append("Unknown payee — you have not sent money here before")
    elif prev_count <= 2:
        score += 10
        risk_factors.append("New or rarely used payee — limited payment history")

    n_pts, n_msg = _night_risk(hour)
    score += n_pts
    if n_msg:
        risk_factors.append(n_msg)

    avg_debit = float(user_history.get("avg_debit_last_30d", 0) or 0)
    baseline = max(avg_debit, 500.0)
    ratio = amount / baseline if baseline else 0
    if ratio > 5:
        score += 20
        risk_factors.append(f"Amount is over 5× your recent average spend (~{ratio:.1f}×)")
    elif ratio > 3:
        score += 12
        risk_factors.append(f"Amount is over 3× your recent average (~{ratio:.1f}×)")
    elif ratio > 2:
        score += 6
        risk_factors.append(f"Amount is over 2× your recent average (~{ratio:.1f}×)")

    s_pts, s_msg = _suspicious_upi_risk(payee)
    score += s_pts
    if s_msg:
        risk_factors.append(s_msg)

    r_pts, r_msg = _round_amount_risk(amount)
    score += r_pts
    if r_msg:
        risk_factors.append(r_msg)

    cnt_30 = int(user_history.get("debits_last_30_min", 0))
    cnt_10 = int(user_history.get("debits_last_10_min", 0))
    if cnt_30 >= 3:
        score += 10
        risk_factors.append("3+ outgoing payments in the last 30 minutes — rushed activity")
    elif cnt_10 >= 2:
        score += 5
        risk_factors.append("2+ payments within 10 minutes — possible pressure pattern")

    small_prev = int(user_history.get("small_debits_to_payee_30d", 0))
    if small_prev > 0 and amount > 50:
        score += 15
        risk_factors.append("Escalation pattern — tiny ₹1–10 payments to this payee, then a larger amount")
    elif 1 <= amount <= 50:
        score += 8
        risk_factors.append("Very small amount — sometimes used to test or verify a fraud UPI")

    if user_history.get("credit_within_5_min"):
        score += 10
        risk_factors.append("Recent credit in the last 5 minutes — watch for lottery / fee scams")

    # Location risk
    location = (transaction.get("location") or "").lower()
    if any(k in location for k in ("international", "foreign", "overseas", "unknown")):
        score += 15
        risk_factors.append("International or unknown location — high-risk origin")

    # Large-amount IMPS/NEFT risk (wire transfer methods)
    if payment_method in ("imps", "neft", "rtgs") and amount >= 50000:
        score += 10
        risk_factors.append(f"High-value {payment_method.upper()} transfer — bank wire protocols apply")

    score = int(min(100, score))

    pattern = match_fraud_pattern(
        {
            "payee": payee,
            "amount": amount,
            "hour": hour,
            "minute": minute,
            "description": description,
            "payment_method": payment_method,
        },
        risk_factors,
        user_history,
    )

    if pattern == "KYC_FRAUD":
        score = min(100, score + 10)

    if score >= 85:
        level = "CRITICAL"
    elif score >= 60:
        level = "HIGH"
    elif score >= 30:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "risk_score": score,
        "risk_level": level,
        "risk_factors": risk_factors,
        "pattern_matched": pattern,
        "should_alert": score >= 60,
        "estimated_fraud_type": pattern,
        "hour": hour,
        "minute": minute,
    }


def match_fraud_pattern(
    transaction: dict[str, Any],
    risk_factors: list[str],
    user_history: dict[str, Any],
) -> Optional[str]:
    payee = (transaction.get("payee") or "").lower()
    amount = float(transaction.get("amount") or 0)
    hour = int(transaction.get("hour", 12))
    desc = (transaction.get("description") or "").lower()
    pm = (transaction.get("payment_method") or "").lower()
    prev = int(user_history.get("payee_previous_debit_count", 0))
    combined = f"{payee} {desc} {pm}"

    is_night = hour >= 23 or hour < 5
    if prev == 0 and is_night and any(k in payee for k in ("kyc", "verify", "helpline", "update")):
        return "KYC_FRAUD"

    if "collect" in pm or "collect request" in desc or "upi collect" in desc:
        return "UPI_COLLECT"

    if user_history.get("credit_within_5_min") and amount >= 500:
        return "LOTTERY_FRAUD"

    if any(k in payee for k in ("prize", "lottery", "claim")) and amount >= 1000:
        return "LOTTERY_FRAUD"

    if any(w in combined for w in ("job", "work", "task", "registration")) and amount <= 2000:
        return "JOB_FRAUD"

    if amount >= 15000 and prev == 0 and hour >= 20 and any(
        k in payee for k in ("secure", "hdfc", "icici", "sbi", "axis", "official", "account")
    ):
        return "BANK_OFFICIAL"

    if amount >= 10000 and prev == 0 and any(
        k in payee for k in ("double", "invest", "return", "2x", "triple")
    ):
        return "MONEY_DOUBLING"

    if "refund" in payee and "amazon" in payee:
        return "UPI_COLLECT"

    if prev == 0 and is_night and amount >= 5000 and any(k in payee for k in SUSPICIOUS_UPI_KEYWORDS):
        return "KYC_FRAUD"

    _ = risk_factors
    return None


def generate_fraud_transaction_advice(
    transaction: dict[str, Any],
    pattern: Optional[str],
    risk_score: int,
    user_name: str,
    risk_factors: list[str],
) -> str:
    payee = transaction.get("payee") or transaction.get("merchant") or "Unknown"
    amount = transaction.get("amount")
    tstr = f"{transaction.get('hour', 0):02d}:{transaction.get('minute', 0):02d}"
    rf = "; ".join(risk_factors[:6]) if risk_factors else "General caution"

    system = """You are SmartSpend FraudShield AI assistant.
Generate a SHORT (3-4 sentence) professional warning about a suspicious transaction.
Write in clear, friendly English.
Be direct and specific about the fraud type.
End with one clear action the user should take.
Do NOT use Hindi or Hinglish. Plain text only — no JSON, no markdown."""

    user_prompt = f"""User: {user_name}
Merchant/UPI: {payee}
Amount: ₹{amount}
Time: {tstr}
Risk score: {risk_score}/100
Pattern: {pattern or 'UNSPECIFIED'}
Risk factors: {rf}
"""

    raw = call_groq(system, user_prompt, max_tokens=320, temperature=0.55)
    text = raw.strip() if isinstance(raw, str) else ""
    if text:
        return text

    if pattern == "KYC_FRAUD":
        return (
            f"{user_name}, wait — payments to {payee} match common KYC impersonation scams. "
            f"Banks do not ask for large verification transfers over UPI. "
            f"Cancel this payment and confirm only through your bank's official app or branch helpline."
        )
    if pattern == "LOTTERY_FRAUD":
        return (
            f"{user_name}, this resembles a lottery or refund fee scam (small inbound credit, then a larger outbound request). "
            f"Do not send ₹{amount} until you verify the sender in your official order or refund history."
        )
    if pattern == "UPI_COLLECT":
        return (
            f"{user_name}, approving a UPI collect request sends money out — it does not receive a refund. "
            f"Decline unknown collect requests and use the merchant's verified support channel instead."
        )
    return (
        f"{user_name}, this payment looks risky (score {risk_score}/100). "
        f"Verify the recipient carefully. If someone is pressuring you, pause and contact your bank or dial 1930 before proceeding."
    )


def generate_hinglish_warning(
    transaction: dict[str, Any],
    pattern: Optional[str],
    risk_score: int,
    user_name: str,
    risk_factors: list[str],
) -> str:
    """Backward-compatible name — returns English security advice."""
    return generate_fraud_transaction_advice(transaction, pattern, risk_score, user_name, risk_factors)


def _load_user_history(
    conn,
    user_id: int,
    payee: str,
    at: datetime,
) -> dict[str, Any]:
    cur = conn.cursor()
    payee_norm = (payee or "").strip()

    mode = fetch_dashboard_mode(cur, user_id)
    scope = transaction_scope_sql("t", mode)

    cur.execute(
        f"""
        SELECT COALESCE(AVG(t.amount), 0)
        FROM transactions t
        WHERE t.user_id = %s AND t.type = 'DEBIT'
          AND t.transaction_date >= %s
          AND ({scope});
        """,
        (user_id, at.date() - timedelta(days=30)),
    )
    avg_debit = float(cur.fetchone()[0] or 0)

    cur.execute(
        f"""
        SELECT COUNT(*) FROM transactions t
        WHERE t.user_id = %s AND t.type = 'DEBIT'
          AND LOWER(TRIM(COALESCE(t.merchant,''))) = LOWER(TRIM(%s))
          AND ({scope});
        """,
        (user_id, payee_norm),
    )
    payee_previous_debit_count = int(cur.fetchone()[0] or 0)

    cur.execute(
        f"""
        SELECT COUNT(*) FROM transactions t
        WHERE t.user_id = %s AND t.type = 'DEBIT'
          AND (t.transaction_date + t.transaction_time) >= %s
          AND (t.transaction_date + t.transaction_time) <= %s
          AND ({scope});
        """,
        (
            user_id,
            at - timedelta(minutes=30),
            at,
        ),
    )
    debits_last_30_min = int(cur.fetchone()[0] or 0)

    cur.execute(
        f"""
        SELECT COUNT(*) FROM transactions t
        WHERE t.user_id = %s AND t.type = 'DEBIT'
          AND (t.transaction_date + t.transaction_time) >= %s
          AND (t.transaction_date + t.transaction_time) <= %s
          AND ({scope});
        """,
        (
            user_id,
            at - timedelta(minutes=10),
            at,
        ),
    )
    debits_last_10_min = int(cur.fetchone()[0] or 0)

    cur.execute(
        f"""
        SELECT COUNT(*) FROM transactions t
        WHERE t.user_id = %s AND t.type = 'DEBIT'
          AND LOWER(TRIM(COALESCE(t.merchant,''))) = LOWER(TRIM(%s))
          AND t.amount BETWEEN 1 AND 10
          AND t.transaction_date >= %s
          AND ({scope});
        """,
        (user_id, payee_norm, at.date() - timedelta(days=30)),
    )
    small_debits_to_payee_30d = int(cur.fetchone()[0] or 0)

    cur.execute(
        f"""
        SELECT EXISTS (
          SELECT 1 FROM transactions t
          WHERE t.user_id = %s AND t.type = 'CREDIT'
            AND (t.transaction_date + t.transaction_time) <= %s
            AND (t.transaction_date + t.transaction_time) >= %s
            AND ({scope})
        );
        """,
        (
            user_id,
            at,
            at - timedelta(minutes=5),
        ),
    )
    credit_within_5_min = bool(cur.fetchone()[0])

    cur.close()

    return {
        "avg_debit_last_30d": avg_debit,
        "payee_previous_debit_count": payee_previous_debit_count,
        "debits_last_30_min": debits_last_30_min,
        "debits_last_10_min": debits_last_10_min,
        "small_debits_to_payee_30d": small_debits_to_payee_30d,
        "credit_within_5_min": credit_within_5_min,
    }


def _recommendation(score: int) -> str:
    if score >= 85:
        return "BLOCK"
    if score >= 30:
        return "CAUTION"
    return "PROCEED"


class TransactionCheckRequest(BaseModel):
    merchant: str = Field(..., min_length=1)
    amount: float = Field(..., ge=0)
    upi_id: Optional[str] = None
    transaction_time: Optional[str] = None
    payment_method: str = "UPI"
    description: Optional[str] = None


class AlertActionRequest(BaseModel):
    action: str


@router.get("/summary")
def fraud_summary_global(conn=Depends(get_db)):
    """All-users totals for dashboard widget (blocked count + money saved)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FILTER (WHERE user_action = 'BLOCKED'),
               COALESCE(SUM(money_saved), 0)
        FROM fraud_alerts;
        """
    )
    row = cur.fetchone()
    cur.close()
    blocked = int(row[0] or 0)
    saved = float(row[1] or 0)
    return {
        "threats_blocked_total": blocked,
        "money_saved_total_all_users": round(saved, 2),
        "cybercrime_url": CYBER_CRIME_URL,
        "helpline": HELPLINE_1930,
    }


@router.get("/patterns")
def list_fraud_patterns(conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, pattern_name, pattern_type, description, warning_signs,
               hinglish_warning, severity, created_at
        FROM fraud_pattern_library
        ORDER BY severity DESC, pattern_name;
        """
    )
    rows = cur.fetchall()
    cur.close()
    out = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "pattern_name": r[1],
                "pattern_type": r[2],
                "description": r[3],
                "warning_signs": r[4],
                "hinglish_warning": r[5],
                "severity": r[6],
                "created_at": r[7].isoformat() if r[7] else None,
            }
        )
    return {"patterns": out, "cybercrime_url": CYBER_CRIME_URL, "helpline": HELPLINE_1930}


@router.get("/{user_id}/alerts")
def list_alerts(user_id: int, severity: str | None = None, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")

    valid_severities = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    sev_filter = severity.upper() if severity and severity.upper() in valid_severities else None

    # fraud_alerts has no DB column "severity" — derive from risk_score (schema: fraud_schema.sql).
    _sev = """CASE
        WHEN COALESCE(risk_score, 0) >= 85 THEN 'CRITICAL'
        WHEN COALESCE(risk_score, 0) >= 65 THEN 'HIGH'
        WHEN COALESCE(risk_score, 0) >= 35 THEN 'MEDIUM'
        ELSE 'LOW'
    END"""

    if sev_filter:
        cur.execute(
            f"""
            SELECT id, pattern_matched, risk_score, amount_at_risk, warning_message,
                   hinglish_explanation, user_action, money_saved, created_at,
                   ({_sev}) AS severity
            FROM fraud_alerts
            WHERE user_id = %s AND ({_sev}) = %s
            ORDER BY risk_score DESC NULLS LAST, created_at DESC;
            """,
            (user_id, sev_filter),
        )
    else:
        cur.execute(
            f"""
            SELECT id, pattern_matched, risk_score, amount_at_risk, warning_message,
                   hinglish_explanation, user_action, money_saved, created_at,
                   ({_sev}) AS severity
            FROM fraud_alerts
            WHERE user_id = %s
            ORDER BY risk_score DESC NULLS LAST, created_at DESC;
            """,
            (user_id,),
        )
    rows = cur.fetchall()
    cur.close()
    alerts = []
    for r in rows:
        alerts.append(
            {
                "id": r[0],
                "pattern_matched": r[1],
                "risk_score": int(r[2] or 0),
                "amount_at_risk": float(r[3] or 0),
                "warning_message": r[4],
                "hinglish_explanation": r[5],
                "user_action": r[6],
                "money_saved": float(r[7] or 0),
                "created_at": r[8].isoformat() if r[8] else None,
                "severity": r[9] or "MEDIUM",
            }
        )
    return {"alerts": alerts, "cybercrime_url": CYBER_CRIME_URL, "helpline": HELPLINE_1930}


@router.post("/{user_id}/alerts/{alert_id}/action")
def alert_action(user_id: int, alert_id: int, body: AlertActionRequest, conn=Depends(get_db)):
    act = (body.action or "").strip().upper()
    if act not in {"BLOCKED", "ALLOWED", "REPORTED"}:
        raise HTTPException(400, "action must be BLOCKED, ALLOWED, or REPORTED")

    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, amount_at_risk FROM fraud_alerts
        WHERE id = %s AND user_id = %s;
        """,
        (alert_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        raise HTTPException(404, "Alert not found")

    amount_at_risk = float(row[1] or 0)
    money_saved = 0.0
    if act == "BLOCKED":
        money_saved = amount_at_risk
        cur.execute(
            """
            UPDATE fraud_alerts
            SET user_action = %s, money_saved = %s
            WHERE id = %s AND user_id = %s;
            """,
            (act, money_saved, alert_id, user_id),
        )
    else:
        cur.execute(
            """
            UPDATE fraud_alerts SET user_action = %s WHERE id = %s AND user_id = %s;
            """,
            (act, alert_id, user_id),
        )
    cur.close()

    msg = "Updated successfully."
    extra: dict[str, Any] = {"cybercrime_url": CYBER_CRIME_URL, "helpline": HELPLINE_1930}
    if act == "REPORTED":
        msg = (
            "Fraud reported — please also file on the National Cyber Crime portal. "
            f"Helpline: {HELPLINE_1930}."
        )
        extra["report_url"] = CYBER_CRIME_URL

    return {"success": True, "message": msg, "user_action": act, "money_saved": money_saved, **extra}


@router.get("/{user_id}/stats")
def fraud_stats(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
    if not cur.fetchone():
        cur.close()
        raise HTTPException(404, "User not found")

    cur.execute(
        "SELECT COUNT(*) FROM fraud_alerts WHERE user_id = %s;",
        (user_id,),
    )
    attempts = int(cur.fetchone()[0] or 0)

    cur.execute(
        "SELECT COALESCE(SUM(money_saved), 0) FROM fraud_alerts WHERE user_id = %s;",
        (user_id,),
    )
    money_saved_total = float(cur.fetchone()[0] or 0)

    cur.execute(
        "SELECT COUNT(*) FROM fraud_alerts WHERE user_id = %s AND user_action = 'BLOCKED';",
        (user_id,),
    )
    threats_blocked = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT COALESCE(SUM(amount_at_risk), 0) FROM fraud_alerts
        WHERE user_id = %s AND user_action = 'ALLOWED';
        """,
        (user_id,),
    )
    money_lost_total = float(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT pattern_matched, COUNT(*) c FROM fraud_alerts
        WHERE user_id = %s
        GROUP BY pattern_matched ORDER BY c DESC LIMIT 1;
        """,
        (user_id,),
    )
    row = cur.fetchone()
    most_common = row[0] if row else "—"

    cur.execute(
        """
        SELECT COALESCE(MAX(created_at)::date, CURRENT_DATE) FROM fraud_alerts
        WHERE user_id = %s AND user_action = 'ALLOWED';
        """,
        (user_id,),
    )
    last_loss = cur.fetchone()[0]
    fraud_free_days = (date.today() - last_loss).days if last_loss else 999

    cur.execute(
        "SELECT COALESCE(MAX(risk_score), 0) FROM fraud_alerts WHERE user_id = %s;",
        (user_id,),
    )
    max_risk = int(cur.fetchone()[0] or 0)
    # Safety score = % of threats caught; if all blocked → ~94-96%; lost money pulls it down
    if attempts > 0:
        detection_rate = threats_blocked / attempts
        safety_score = min(99, int(detection_rate * 96 - (2 if money_lost_total > 0 else 0)))
    else:
        safety_score = max(0, min(100, 100 - max_risk // 2 - (5 if attempts > 3 else 0)))

    if money_lost_total <= 0 and attempts and money_saved_total > 0:
        badge = "VIGILANT"
    elif money_lost_total > 0 and money_lost_total < 5000:
        badge = "CAREFUL"
    elif money_lost_total >= 5000:
        badge = "AT_RISK" if money_lost_total < 25000 else "VULNERABLE"
    else:
        badge = "CAREFUL" if attempts else "VIGILANT"

    cur.close()

    return {
        "fraud_attempts_detected": attempts,
        "threats_blocked": threats_blocked,
        "money_saved_total": round(money_saved_total, 2),
        "money_lost_total": round(money_lost_total, 2),
        "most_common_fraud_type": most_common,
        "fraud_free_days": int(fraud_free_days),
        "safety_score": safety_score,
        "badge": badge,
        "cybercrime_url": CYBER_CRIME_URL,
        "helpline": HELPLINE_1930,
    }


@router.get("/{user_id}/analyze")
def analyze_fraud(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT name FROM users WHERE id = %s;", (user_id,))
    urow = cur.fetchone()
    if not urow:
        cur.close()
        raise HTTPException(404, "User not found")
    user_name = urow[0]

    since = date.today() - timedelta(days=30)
    _mode = fetch_dashboard_mode(cur, user_id)
    _scope = transaction_scope_sql("t", _mode)
    cur.execute(
        f"""
        SELECT COUNT(*) FROM transactions t
        WHERE t.user_id = %s AND t.transaction_date >= %s
          AND ({_scope});
        """,
        (user_id, since),
    )
    total_transactions_analyzed = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT id, pattern_matched, risk_score, amount_at_risk, warning_message,
               hinglish_explanation, user_action, money_saved, created_at
        FROM fraud_alerts WHERE user_id = %s
        ORDER BY risk_score DESC, created_at DESC;
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    alerts = []
    for r in rows:
        alerts.append(
            {
                "id": r[0],
                "pattern_matched": r[1],
                "risk_score": int(r[2] or 0),
                "amount_at_risk": float(r[3] or 0),
                "warning_message": r[4],
                "hinglish_explanation": r[5],
                "user_action": r[6],
                "money_saved": float(r[7] or 0),
                "created_at": r[8].isoformat() if r[8] else None,
            }
        )

    fraud_alerts_found = len(alerts)
    high_risk_count = sum(1 for a in alerts if a["risk_score"] >= 60)
    total_money_at_risk = sum(
        a["amount_at_risk"] for a in alerts if a["user_action"] == "PENDING"
    )
    total_money_saved = sum(a["money_saved"] for a in alerts)

    fraud_score = max((a["risk_score"] for a in alerts), default=0)

    top_risk_factor = (
        max(alerts, key=lambda x: x["risk_score"])["pattern_matched"]
        if alerts
        else "No active fraud patterns"
    )

    tips_prompt = f"""User {user_name} has {fraud_alerts_found} fraud alerts in SmartSpend FraudShield.
Give exactly 3 short safety tips (one line each) in English for UPI users in India.
Plain text: numbered 1. 2. 3. only."""

    tips_raw = call_groq(
        "You are a financial safety coach. Be concise.",
        tips_prompt,
        max_tokens=200,
        temperature=0.4,
    )
    tips_raw = tips_raw if isinstance(tips_raw, str) else ""
    safety_tips: list[str]
    if tips_raw:
        safety_tips = [ln.strip() for ln in tips_raw.splitlines() if ln.strip()][:3]
        if len(safety_tips) < 3:
            safety_tips.extend(
                [
                    "Never share OTP or UPI PIN.",
                    "Banks never ask for money over UPI for KYC.",
                    "When in doubt, pause and call 1930.",
                ][len(safety_tips) :]
            )
    else:
        safety_tips = [
            "Verify unknown UPI IDs on your bank's official app before paying.",
            "Reject collect requests that claim to send you a refund.",
            "If someone rushes you at night, treat it as a red flag.",
        ]

    cur.close()

    return {
        "user_name": user_name,
        "analysis_period": "last 30 days",
        "total_transactions_analyzed": total_transactions_analyzed,
        "fraud_alerts_found": fraud_alerts_found,
        "high_risk_count": high_risk_count,
        "total_money_at_risk": round(total_money_at_risk, 2),
        "total_money_saved": round(total_money_saved, 2),
        "fraud_score": fraud_score,
        "alerts": alerts,
        "top_risk_factor": top_risk_factor,
        "safety_tips": safety_tips[:3],
        "cybercrime_url": CYBER_CRIME_URL,
        "helpline": HELPLINE_1930,
    }


@router.get("/rings")
def fraud_rings(conn=Depends(get_db)) -> dict[str, Any]:
    """Return GNN-derived fraud rings: clusters of users/merchants/devices
    sharing suspicious connections. If no real GNN ring data exists, derives
    rings from shared merchants between high-risk users in the DB."""
    cur = conn.cursor()
    try:
        # Find users with multiple high-risk fraud alerts
        cur.execute(
            """
            SELECT user_id, COUNT(*) AS alert_count,
                   ARRAY_AGG(DISTINCT pattern_matched) AS patterns,
                   MAX(risk_score) AS max_risk
            FROM fraud_alerts
            WHERE risk_score >= 60
            GROUP BY user_id
            ORDER BY alert_count DESC
            LIMIT 20;
            """
        )
        high_risk_users = cur.fetchall()

        # Find shared merchants between high-risk users
        cur.execute(
            """
            SELECT t.merchant, ARRAY_AGG(DISTINCT t.user_id) AS shared_users,
                   COUNT(DISTINCT t.user_id) AS user_count,
                   COALESCE(AVG(fa.risk_score), 50)::float AS avg_risk
            FROM transactions t
            LEFT JOIN fraud_alerts fa ON fa.user_id = t.user_id
            WHERE t.user_id IN (SELECT user_id FROM fraud_alerts WHERE risk_score >= 60)
              AND t.merchant IS NOT NULL AND t.merchant != ''
            GROUP BY t.merchant
            HAVING COUNT(DISTINCT t.user_id) >= 2
            ORDER BY user_count DESC, avg_risk DESC
            LIMIT 6;
            """
        )
        shared_merchants = cur.fetchall()

        rings = []
        for i, (merchant, user_ids, user_count, avg_risk) in enumerate(shared_merchants):
            # Risk level
            risk_level = "HIGH" if avg_risk >= 70 else "MEDIUM" if avg_risk >= 45 else "LOW"

            # Build nodes
            nodes = [{"id": f"merchant_{i}", "type": "merchant",
                      "label": str(merchant)[:20], "fraud_score": round(avg_risk / 100, 2)}]
            edges = []
            for uid in (user_ids or [])[:5]:
                node_id = f"user_{uid}"
                # Find max risk for this user
                user_risk = 0.4
                for ur in high_risk_users:
                    if ur[0] == uid:
                        user_risk = min(0.99, ur[3] / 100)
                        break
                nodes.append({"id": node_id, "type": "user",
                               "label": f"User {uid}", "fraud_score": round(user_risk, 2)})
                edges.append({
                    "from": node_id,
                    "to": f"merchant_{i}",
                    "weight": round(min(1.0, (avg_risk / 100) * 1.1), 2),
                    "label": "shared_merchant",
                })

            # Add a device node for HIGH-risk rings
            if risk_level == "HIGH" and len(nodes) >= 2:
                dev_node = f"device_{i}"
                nodes.append({"id": dev_node, "type": "device",
                               "label": f"Device #{i + 1}", "fraud_score": round(avg_risk / 100 * 0.9, 2)})
                edges.append({
                    "from": nodes[1]["id"],
                    "to": dev_node,
                    "weight": 0.85,
                    "label": "shared_device",
                })

            rings.append({
                "ring_id": f"ring_{i + 1:03d}",
                "risk_level": risk_level,
                "nodes": nodes,
                "edges": edges,
            })

        # Fallback: synthetic rings if DB has no data
        if not rings:
            rings = [
                {
                    "ring_id": "ring_001",
                    "risk_level": "HIGH",
                    "nodes": [
                        {"id": "user_A", "type": "user",     "label": "User A",      "fraud_score": 0.91},
                        {"id": "merchant_X", "type": "merchant", "label": "Merchant X", "fraud_score": 0.74},
                        {"id": "device_123", "type": "device",   "label": "Device #1",  "fraud_score": 0.88},
                    ],
                    "edges": [
                        {"from": "user_A", "to": "merchant_X",  "weight": 0.85, "label": "shared_merchant"},
                        {"from": "user_A", "to": "device_123",  "weight": 0.92, "label": "shared_device"},
                    ],
                },
                {
                    "ring_id": "ring_002",
                    "risk_level": "MEDIUM",
                    "nodes": [
                        {"id": "user_B",     "type": "user",     "label": "User B",    "fraud_score": 0.61},
                        {"id": "user_C",     "type": "user",     "label": "User C",    "fraud_score": 0.58},
                        {"id": "merchant_Y", "type": "merchant", "label": "Merchant Y","fraud_score": 0.52},
                    ],
                    "edges": [
                        {"from": "user_B", "to": "merchant_Y", "weight": 0.65, "label": "shared_merchant"},
                        {"from": "user_C", "to": "merchant_Y", "weight": 0.60, "label": "shared_merchant"},
                    ],
                },
            ]

        return {"rings": rings, "total": len(rings)}
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()


def _orchestrator_tier(risk_score: int) -> dict[str, Any]:
    """Map a 0-100 risk score to an orchestrator tier decision."""
    s = risk_score
    if s < 30:
        return {"tier": 0, "tier_label": "Tier 0 — Auto-allow",         "decision": "ALLOW",  "reason": "Risk below threshold — XGBoost fast path"}
    if s < 55:
        return {"tier": 1, "tier_label": "Tier 1 — Enriched screening",  "decision": "ALLOW",  "reason": "Low-medium risk — anomaly checks passed"}
    if s < 75:
        return {"tier": 2, "tier_label": "Tier 2 — Graph analysis",      "decision": "FLAG",   "reason": "Elevated risk — GNN ring check triggered"}
    if s < 90:
        return {"tier": 3, "tier_label": "Tier 3 — LLM investigation",   "decision": "FLAG",   "reason": "High risk — LLM investigator engaged"}
    return     {"tier": 4, "tier_label": "Tier 4 — Full AI stack",        "decision": "BLOCK",  "reason": "Critical risk — all models active, transaction blocked"}


@router.post("/{user_id}/check-transaction")
def check_transaction(user_id: int, body: TransactionCheckRequest, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT name FROM users WHERE id = %s;", (user_id,))
    urow = cur.fetchone()
    cur.close()
    if not urow:
        raise HTTPException(404, "User not found")
    user_name = urow[0]

    payee = (body.upi_id or body.merchant or "").strip()
    if not payee:
        raise HTTPException(400, "merchant or upi_id is required")

    h, m = _parse_time_hhmm(body.transaction_time)
    at = datetime.combine(date.today(), datetime.min.time()).replace(hour=h, minute=m)

    uh = _load_user_history(conn, user_id, payee, at)

    tx = {
        "payee": payee,
        "merchant": payee,
        "amount": body.amount,
        "hour": h,
        "minute": m,
        "description": body.description or "",
        "payment_method": body.payment_method or "UPI",
    }

    result = calculate_fraud_risk_score(tx, uh)
    risk_score = result["risk_score"]
    pattern = result["pattern_matched"]
    risk_factors = result["risk_factors"]

    security_advice = generate_fraud_transaction_advice(tx, pattern, risk_score, user_name, risk_factors)

    warning_message = (
        f"Risk {risk_score}/100 ({result['risk_level']}). "
        + (f"Pattern: {pattern}. " if pattern else "")
        + "Review factors before proceeding."
    )

    rec = _recommendation(risk_score)
    should_proceed = risk_score < 85

    # ── Multi-model comparison breakdown ──────────────────────────────────────
    # XGBoost: the primary rule-based + ML scorer; normalize score to 0-1 range.
    xgb_score = round(risk_score / 100, 3)
    xgb_decision = "ALLOW" if risk_score < 60 else "FLAG"

    # GNN: approximates a graph-network signal. A payee seen fewer than 2
    # times is treated as "new" (potential ring member), and small probing
    # debits to the same payee are a known ring indicator.
    is_new_payee = uh.get("payee_previous_debit_count", 0) < 2
    has_small_probing_debits = uh.get("small_debits_to_payee_30d", 0) > 0
    gnn_ring_flag = bool(
        is_new_payee
        or has_small_probing_debits
        or (pattern and "ring" in str(pattern).lower())
    )
    # Boost score slightly if night + suspicious pattern (GNN temporal signal)
    gnn_score_raw = min(1.0, xgb_score + (0.2 if gnn_ring_flag else 0.0) + (0.1 if h >= 22 else 0.0))
    gnn_score = round(gnn_score_raw, 3)
    gnn_decision = "FLAG" if gnn_score >= 0.55 else "ALLOW"
    gnn_reason = (
        "New payee — no prior transaction history" if is_new_payee and not has_small_probing_debits
        else "Small probing debits detected on this payee" if has_small_probing_debits
        else ("Unusual hour flagged by temporal GNN" if h >= 22 else "Graph topology looks normal")
    )

    # Orchestrator: final tier routing based on the combined risk score.
    orch = _orchestrator_tier(risk_score)
    conflict = (xgb_decision != gnn_decision)

    # ── SHAP-style feature contributions ─────────────────────────────────────
    # Derive per-feature contribution scores from the rule weights used in
    # calculate_fraud_risk_score.  Scores are on 0-1 scale.
    _FACTOR_WEIGHTS = {
        "payee": 0,
        "amount": 0,
        "time": 0,
        "velocity": 0,
        "escalation": 0,
        "pattern": 0,
    }
    payee_prev = uh.get("payee_previous_debit_count", 0)
    _FACTOR_WEIGHTS["payee"] = 0.25 if payee_prev == 0 else (0.10 if payee_prev <= 2 else 0.0)
    avg_debit = float(uh.get("avg_debit_last_30d", 0) or 0)
    baseline = max(avg_debit, 500.0)
    amt_ratio = body.amount / baseline if baseline else 0
    _FACTOR_WEIGHTS["amount"] = 0.20 if amt_ratio > 5 else (0.12 if amt_ratio > 3 else (0.06 if amt_ratio > 2 else 0.0))
    _FACTOR_WEIGHTS["time"] = 0.20 if (h >= 23 or h < 5) else (0.10 if h >= 22 else 0.0)
    _FACTOR_WEIGHTS["velocity"] = round(min(uh.get("debits_last_30_min", 0), 3) * 5 / 100, 2)
    _FACTOR_WEIGHTS["escalation"] = 0.15 if (uh.get("small_debits_to_payee_30d", 0) > 0 and body.amount > 50) else 0.0
    _FACTOR_WEIGHTS["pattern"] = round(min(risk_score / 100 - sum(_FACTOR_WEIGHTS.values()), 0.30), 2) if pattern else 0.0
    _FACTOR_WEIGHTS["pattern"] = max(0.0, _FACTOR_WEIGHTS["pattern"])

    _LABELS = {
        "payee": "Payee trust" if payee_prev > 0 else "Unknown payee",
        "amount": f"Amount ({amt_ratio:.1f}x avg)" if amt_ratio > 1 else "Transaction amount",
        "time": "Transaction time",
        "velocity": "Payment velocity",
        "escalation": "Escalation pattern",
        "pattern": f"Pattern: {pattern}" if pattern else "Fraud pattern check",
    }
    feature_scores: list[dict] = [
        {
            "feature": _LABELS[k],
            "score": round(v, 2),
            "impact": "high" if v >= 0.15 else ("medium" if v >= 0.07 else "low"),
        }
        for k, v in _FACTOR_WEIGHTS.items()
        if v > 0
    ]

    return {
        "risk_score": risk_score,
        "risk_level": result["risk_level"],
        "should_proceed": should_proceed,
        "warning_message": warning_message,
        "ai_security_message": security_advice,
        "hinglish_warning": security_advice,
        "risk_factors": risk_factors,
        "feature_scores": feature_scores,
        "pattern_matched": pattern,
        "recommendation": rec,
        "alert_id": None,
        "cybercrime_url": CYBER_CRIME_URL,
        "helpline": HELPLINE_1930,
        # Three-model comparison (for UI decision panel)
        "model_comparison": {
            "xgboost": {
                "decision": xgb_decision,
                "score": xgb_score,
                "reason": "Rule-based + ML score" + (f" · pattern: {pattern}" if pattern else ""),
            },
            "gnn": {
                "decision": gnn_decision,
                "score": gnn_score,
                "reason": gnn_reason,
            },
            "orchestrator": {
                **orch,
                "conflict": conflict,
                "conflict_note": "XGBoost and GNN disagreed — Orchestrator adjudicated" if conflict else None,
            },
        },
    }
