"""
After signup bank-link: seed EMI, purchase goals, festival plans, fraud alerts.
All amounts are realistic Indian urban spends; salaries stay under ₹1,00,000/month.
"""

from __future__ import annotations

import calendar
import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from services.new_user_transaction_seed import insert_individual_transactions

logger = logging.getLogger(__name__)

MAX_MONTHLY_SALARY = 99_000.0

# Per pool index (0–6) — varied EMI count, fraud types, goals (not tied to bank slug).
WORKSPACE_BY_POOL_INDEX: tuple[dict[str, Any], ...] = (
    {
        "emis": [
            {
                "loan_name": "Bajaj Pulsar 150",
                "lender_key": "vehicle",
                "principal_amount": 72_000,
                "emi_amount": 2_799,
                "tenure_months": 30,
                "paid_months": 14,
                "loan_type": "vehicle",
                "interest_rate": 9.0,
            },
        ],
        "goals": [
            ("Noise wireless earbuds", 4_499, 0.18, "electronics", "MEDIUM", "Aug 2026"),
            ("Hyderabad weekend trip", 16_500, 0.12, "travel", "LOW", "Sep 2026"),
        ],
        "festival": {"name": "Diwali", "planned": 11_000, "saved": 2_800, "last_year": 9_500},
        "important_days": [
            ("Parents anniversary dinner", 45, False),
            ("Best friend birthday", 120, True),
        ],
        "fraud": [
            {
                "pattern": "geo_anomaly",
                "score": 78,
                "amount": 4_200,
                "severity": "HIGH",
                "action": "PENDING",
                "merchant": "Unknown UPI Jaipur QR",
                "warning": "Payment in Jaipur while your phone is usually in Hyderabad.",
                "hinglish": "Hyderabad mein rehte ho, Jaipur se UPI — yeh suspicious lagta hai!",
            },
        ],
        "flag_txn": {"risk_score": 82, "anomaly": True},
    },
    {
        "emis": [
            {
                "loan_name": "Honda Activa 6G",
                "lender_key": "vehicle",
                "principal_amount": 68_000,
                "emi_amount": 3_199,
                "tenure_months": 24,
                "paid_months": 8,
                "loan_type": "vehicle",
                "interest_rate": 9.5,
            },
        ],
        "goals": [
            ("Nursing certification course", 12_000, 0.25, "education", "HIGH", "Nov 2026"),
            ("Family Onam gifts", 6_500, 0.20, "shopping", "MEDIUM", "Sep 2026"),
        ],
        "festival": {"name": "Onam", "planned": 7_500, "saved": 1_900, "last_year": 6_200},
        "important_days": [
            ("Night shift allowance day", 30, False),
            ("Sister's engagement", 90, False),
        ],
        "fraud": [],
        "flag_txn": None,
    },
    {
        "emis": [
            {
                "loan_name": "Maruti Swift ZXI",
                "lender_key": "vehicle",
                "principal_amount": 580_000,
                "emi_amount": 14_850,
                "tenure_months": 48,
                "paid_months": 10,
                "loan_type": "vehicle",
                "interest_rate": 8.5,
            },
            {
                "loan_name": "Education Loan MBA",
                "lender_key": "education",
                "principal_amount": 4_20_000,
                "emi_amount": 9_800,
                "tenure_months": 60,
                "paid_months": 6,
                "loan_type": "education",
                "interest_rate": 10.0,
            },
        ],
        "goals": [
            ("Europe holiday fund", 85_000, 0.22, "travel", "MEDIUM", "Mar 2027"),
            ("Home AC upgrade", 38_000, 0.15, "appliance", "HIGH", "Jun 2026"),
        ],
        "festival": {"name": "Durga Puja", "planned": 18_000, "saved": 5_500, "last_year": 16_200},
        "important_days": [
            ("Parents anniversary", 60, True),
            ("Cousin's wedding", 75, False),
        ],
        "fraud": [
            {
                "pattern": "night_transfer",
                "score": 92,
                "amount": 28_500,
                "severity": "CRITICAL",
                "action": "PENDING",
                "merchant": "IMPS Unknown Payee",
                "warning": "Large IMPS at 2:14 AM to an unregistered UPI handle.",
                "hinglish": "Raat 2 baje ₹28,500 ka transfer — turant bank ko call karo!",
            },
            {
                "pattern": "velocity_attack",
                "score": 74,
                "amount": 9_200,
                "severity": "HIGH",
                "action": "DISMISSED",
                "merchant": "PhonePe Rapid UPI",
                "warning": "Three UPI debits within 6 minutes to same merchant.",
                "hinglish": "6 minute mein teen payment — verify kiya aapne?",
            },
        ],
        "flag_txn": {"risk_score": 91, "anomaly": True},
    },
    {
        "emis": [
            {
                "loan_name": "Samsung Galaxy S24",
                "lender_key": "consumer",
                "principal_amount": 42_000,
                "emi_amount": 3_899,
                "tenure_months": 12,
                "paid_months": 4,
                "loan_type": "consumer_durable",
                "interest_rate": 0.0,
            },
        ],
        "goals": [
            ("CA final exam fees", 22_000, 0.30, "education", "HIGH", "Jul 2026"),
            ("Office formal wear", 8_500, 0.10, "shopping", "MEDIUM", "Aug 2026"),
        ],
        "festival": {"name": "Navratri", "planned": 9_000, "saved": 2_200, "last_year": 7_800},
        "important_days": [
            ("Chartered Accountants Day dinner", 55, True),
        ],
        "fraud": [
            {
                "pattern": "duplicate_charge",
                "score": 62,
                "amount": 1_299,
                "severity": "MEDIUM",
                "action": "PENDING",
                "merchant": "Amazon India",
                "warning": "Same amount charged twice within 4 hours on Amazon.",
                "hinglish": "Amazon ne do baar same amount charge kiya — refund check karo.",
            },
        ],
        "flag_txn": {"risk_score": 68, "anomaly": True},
    },
    {
        "emis": [
            {
                "loan_name": "Home furniture EMI",
                "lender_key": "consumer",
                "principal_amount": 58_000,
                "emi_amount": 2_499,
                "tenure_months": 24,
                "paid_months": 9,
                "loan_type": "consumer_durable",
                "interest_rate": 11.5,
            },
        ],
        "goals": [
            ("Child school fees buffer", 25_000, 0.20, "education", "HIGH", "Jun 2026"),
            ("Family Varanasi trip", 14_000, 0.08, "travel", "MEDIUM", "Oct 2026"),
        ],
        "festival": {"name": "Diwali", "planned": 10_500, "saved": 3_100, "last_year": 9_000},
        "important_days": [
            ("Wife's birthday", 40, True),
            ("Government bonus expected", 15, False),
        ],
        "fraud": [
            {
                "pattern": "lottery_scam",
                "score": 85,
                "amount": 2_200,
                "severity": "HIGH",
                "action": "CONFIRMED",
                "merchant": "Lucky Draw Prize UPI",
                "warning": "Payment to lottery-style UPI — classic advance-fee pattern.",
                "hinglish": "Lucky draw ke naam pe paise gaye — yeh scam tha, report ho chuka hai.",
            },
        ],
        "flag_txn": {"risk_score": 86, "anomaly": True},
    },
    {
        "emis": [],
        "goals": [
            ("Second-hand laptop", 28_000, 0.12, "electronics", "HIGH", "Dec 2026"),
            ("Raj Mandir movie fund", 1_200, 0.50, "entertainment", "LOW", "Next month"),
        ],
        "festival": {"name": "Holi", "planned": 3_500, "saved": 800, "last_year": 2_900},
        "important_days": [
            ("PG rent due reminder", 20, False),
        ],
        "fraud": [
            {
                "pattern": "advance_fee_fraud",
                "score": 75,
                "amount": 799,
                "severity": "HIGH",
                "action": "PENDING",
                "merchant": "Paytm Loan Processing",
                "warning": "Loan processing fee with no loan disbursed.",
                "hinglish": "Loan fee diya par loan nahi mila — fraud ho sakta hai.",
            },
        ],
        "flag_txn": {"risk_score": 76, "anomaly": True},
    },
    {
        "emis": [
            {
                "loan_name": "Commercial vehicle loan",
                "lender_key": "vehicle",
                "principal_amount": 3_20_000,
                "emi_amount": 6_850,
                "tenure_months": 60,
                "paid_months": 22,
                "loan_type": "vehicle",
                "interest_rate": 10.5,
            },
        ],
        "goals": [
            ("Shop inventory restock", 45_000, 0.18, "business", "HIGH", "Jul 2026"),
            ("Family gold purchase", 32_000, 0.10, "shopping", "MEDIUM", "Oct 2026"),
        ],
        "festival": {"name": "Uttarayan", "planned": 8_000, "saved": 2_400, "last_year": 6_800},
        "important_days": [
            ("Wholesale market payment day", 25, False),
            ("Daughter's school annual day", 50, False),
        ],
        "fraud": [
            {
                "pattern": "seller_fraud",
                "score": 80,
                "amount": 5_400,
                "severity": "HIGH",
                "action": "PENDING",
                "merchant": "Meesho Seller SuratTex",
                "warning": "Seller marked delivered but you reported item not received.",
                "hinglish": "Seller ne jhootha delivery dikhaya — paisa wapas maango.",
            },
        ],
        "flag_txn": {"risk_score": 79, "anomaly": True},
    },
)


def _cols(cur: Any, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return {str(r[0]) for r in cur.fetchall()}


def _pool_index(profile: dict[str, Any]) -> int:
    return int(profile["pool_user_id"]) - 900_001


def _workspace_for_profile(profile: dict[str, Any]) -> dict[str, Any]:
    idx = _pool_index(profile) % len(WORKSPACE_BY_POOL_INDEX)
    return WORKSPACE_BY_POOL_INDEX[idx]


def _clamp_salary(income: float) -> float:
    return min(max(income, 12_000.0), MAX_MONTHLY_SALARY)


def _month_dates(today: date, n_months: int, day: int) -> list[date]:
    out: list[date] = []
    y, m = today.year, today.month
    for i in range(n_months - 1, -1, -1):
        yy, mm = y, m - i
        while mm < 1:
            mm += 12
            yy -= 1
        dim = calendar.monthrange(yy, mm)[1]
        out.append(date(yy, mm, min(day, dim)))
    return out


def _emi_txn_count(cur: Any, user_id: int) -> int:
    cur.execute(
        """
        SELECT COUNT(*) FROM transactions
        WHERE user_id = %s
          AND transaction_date >= (CURRENT_DATE - INTERVAL '10 months')
          AND (
            LOWER(COALESCE(description,'')) LIKE '%emi%'
            OR LOWER(COALESCE(description,'')) LIKE '%nach%'
            OR LOWER(COALESCE(description,'')) LIKE '%ecs%'
            OR LOWER(COALESCE(merchant,'')) LIKE '%emi%'
          )
        """,
        (user_id,),
    )
    return int(cur.fetchone()[0] or 0)


def _seed_emi_transactions(
    cur: Any,
    user_id: int,
    bank_label: str,
    display_name: str,
    emis: list[dict[str, Any]],
) -> int:
    if not emis or _emi_txn_count(cur, user_id) >= len(emis) * 4:
        return 0
    today = date.today()
    specs: list[dict[str, Any]] = []
    for emi in emis:
        amt = float(emi["emi_amount"])
        loan = str(emi["loan_name"])
        for d in _month_dates(today, 6, 5):
            specs.append(
                {
                    "transaction_date": d,
                    "transaction_time": time(9, 5, 0),
                    "amount": amt,
                    "merchant": bank_label,
                    "category": "Finance",
                    "type": "DEBIT",
                    "description": f"EMI NACH AutoDebit — {loan}",
                }
            )
    return insert_individual_transactions(cur, user_id, specs)


def _seed_emis_table(
    cur: Any,
    user_id: int,
    bank_label: str,
    emis: list[dict[str, Any]],
) -> int:
    if not emis or "emis" not in _cols(cur, "emis"):
        return 0
    cur.execute("SELECT COUNT(*) FROM emis WHERE user_id = %s AND status = 'active'", (user_id,))
    if int(cur.fetchone()[0] or 0) >= len(emis):
        return 0
    today = date.today()
    n = 0
    for emi in emis:
        next_due = today.replace(day=min(5, 28))
        if next_due < today:
            next_due = (today.replace(day=1) + timedelta(days=32)).replace(day=5)
        start = today - timedelta(days=30 * int(emi.get("paid_months", 6)))
        cur.execute(
            """
            INSERT INTO emis (
              user_id, loan_name, lender, principal_amount, emi_amount,
              tenure_months, paid_months, start_date, next_due_date,
              interest_rate, loan_type, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
            """,
            (
                user_id,
                emi["loan_name"],
                bank_label,
                emi["principal_amount"],
                emi["emi_amount"],
                emi["tenure_months"],
                emi["paid_months"],
                start,
                next_due,
                emi.get("interest_rate", 0),
                emi.get("loan_type", "personal"),
            ),
        )
        n += 1
    return n


def _seed_purchase_goals(
    cur: Any,
    user_id: int,
    income: float,
    goals: list[tuple],
) -> int:
    cur.execute(
        """
        SELECT COUNT(*) FROM purchase_goals
        WHERE user_id = %s AND UPPER(COALESCE(status,'')) <> 'CANCELLED'
        """,
        (user_id,),
    )
    if int(cur.fetchone()[0] or 0) >= 2:
        return 0
    today = date.today()
    pg_cols = _cols(cur, "purchase_goals")
    n = 0
    for item_name, target, saved_pct, cat, priority, buy_window in goals[:2]:
        target = min(float(target), income * 6)
        saved = round(target * saved_pct, 2)
        td = today + timedelta(days=120 if n == 0 else 200)
        months = max((td - today).days / 30.0, 1.0)
        mt = round((target - saved) / months, 2)
        row = {
            "user_id": user_id,
            "item_name": item_name,
            "target_amount": target,
            "saved_amount": saved,
            "target_date": td,
            "monthly_target": mt,
            "category": cat,
            "priority": priority,
            "status": "SAVING",
        }
        if "best_buy_month" in pg_cols:
            row["best_buy_month"] = buy_window
        keys = [k for k in row if k in pg_cols]
        cur.execute(
            f"INSERT INTO purchase_goals ({', '.join(keys)}) VALUES ({', '.join(['%s'] * len(keys))})",
            [row[k] for k in keys],
        )
        n += 1
    return n


def _seed_festival(
    cur: Any,
    user_id: int,
    fest: dict[str, Any],
) -> int:
    if "festival_budgets" not in _cols(cur, "festival_budgets"):
        return 0
    cur.execute(
        "SELECT COUNT(*) FROM festival_budgets WHERE user_id = %s AND festival_date > CURRENT_DATE",
        (user_id,),
    )
    if int(cur.fetchone()[0] or 0) >= 1:
        return 0
    today = date.today()
    diwali = date(2026, 10, 20)
    if fest.get("name") == "Onam":
        fdate = date(2026, 9, 5)
    elif fest.get("name") == "Holi":
        fdate = date(2026, 3, 3)
    elif fest.get("name") == "Navratri":
        fdate = date(2026, 10, 2)
    elif fest.get("name") == "Uttarayan":
        fdate = date(2026, 1, 14)
    elif fest.get("name") == "Durga Puja":
        fdate = date(2026, 10, 1)
    else:
        fdate = diwali
    days_rem = max((fdate - today).days, 1)
    planned = float(fest["planned"])
    saved = float(fest["saved"])
    monthly = round(planned / max(days_rem / 30.0, 0.25), 2)
    cur.execute(
        """
        INSERT INTO festival_budgets (
          user_id, festival_name, festival_date, last_year_spent, planned_budget,
          saved_so_far, monthly_target, days_remaining, status, category_breakdown
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'UPCOMING', %s::jsonb)
        """,
        (
            user_id,
            fest["name"],
            fdate,
            float(fest["last_year"]),
            planned,
            saved,
            monthly,
            days_rem,
            json.dumps({"Gifts": round(planned * 0.35), "Shopping": round(planned * 0.45), "Food": round(planned * 0.20)}),
        ),
    )
    return 1


def _seed_important_days(cur: Any, user_id: int, days: list[tuple]) -> int:
    if "user_important_days" not in _cols(cur, "user_important_days"):
        return 0
    cur.execute("SELECT COUNT(*) FROM user_important_days WHERE user_id = %s", (user_id,))
    if int(cur.fetchone()[0] or 0) >= 2:
        return 0
    today = date.today()
    n = 0
    for title, offset, yearly in days[:2]:
        cur.execute(
            """
            INSERT INTO user_important_days (user_id, title, event_date, notes, repeats_yearly)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, title, today + timedelta(days=offset), "From linked bank profile", yearly),
        )
        n += 1
    return n


def _pick_transaction_ids(cur: Any, user_id: int, limit: int = 3) -> list[int]:
    cur.execute(
        """
        SELECT id FROM transactions
        WHERE user_id = %s AND type = 'DEBIT'
        ORDER BY amount DESC, transaction_date DESC
        LIMIT %s
        """,
        (user_id, limit),
    )
    return [int(r[0]) for r in cur.fetchall()]


def _seed_fraud_alerts(
    cur: Any,
    user_id: int,
    fraud_list: list[dict[str, Any]],
) -> int:
    fa_cols = _cols(cur, "fraud_alerts")
    if not fa_cols or not fraud_list:
        return 0
    cur.execute("SELECT COUNT(*) FROM fraud_alerts WHERE user_id = %s", (user_id,))
    if int(cur.fetchone()[0] or 0) >= len(fraud_list):
        return 0
    txn_ids = _pick_transaction_ids(cur, user_id, max(3, len(fraud_list)))
    if not txn_ids:
        return 0
    n = 0
    now = datetime.now(timezone.utc)
    for i, fr in enumerate(fraud_list):
        txn_id = txn_ids[i % len(txn_ids)]
        row: dict[str, Any] = {
            "user_id": user_id,
            "transaction_id": txn_id,
            "pattern_matched": fr["pattern"],
            "risk_score": fr["score"],
            "amount_at_risk": fr["amount"],
            "warning_message": fr["warning"],
            "hinglish_explanation": fr["hinglish"],
            "user_action": fr.get("action", "PENDING"),
            "money_saved": 0.0 if fr.get("action") == "PENDING" else float(fr["amount"]),
            "severity": fr["severity"],
            "merchant_name": fr.get("merchant"),
            "reason": fr["warning"][:200],
            "verdict": "pending" if fr.get("action") == "PENDING" else "confirmed_fraud",
            "detected_at": now - timedelta(days=3 + i),
        }
        keys = [k for k in row if k in fa_cols]
        cur.execute(
            f"INSERT INTO fraud_alerts ({', '.join(keys)}) VALUES ({', '.join(['%s'] * len(keys))})",
            [row[k] for k in keys],
        )
        n += 1
    return n


def _seed_suspicious_transaction(
    cur: Any,
    user_id: int,
    bank_label: str,
    flag: dict[str, Any] | None,
    fraud_list: list[dict[str, Any]],
) -> int:
    t_cols = _cols(cur, "transactions")
    if not t_cols:
        return 0
    if fraud_list and flag:
        fr = fraud_list[0]
        amt = min(float(fr["amount"]), 35_000.0)
        today = date.today()
        specs = [
            {
                "transaction_date": today - timedelta(days=2),
                "transaction_time": time(2, 14, 0),
                "amount": amt,
                "merchant": fr.get("merchant", "Unknown UPI"),
                "category": "Shopping",
                "type": "DEBIT",
                "description": f"UPI payment — review flagged — {bank_label}",
            }
        ]
        inserted = insert_individual_transactions(cur, user_id, specs)
        if inserted and "risk_score" in t_cols:
            cur.execute(
                """
                SELECT id FROM transactions
                WHERE user_id = %s ORDER BY id DESC LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                updates = ["risk_score = %s"]
                vals: list[Any] = [flag.get("risk_score", 75)]
                if "anomaly_flag" in t_cols:
                    updates.append("anomaly_flag = TRUE")
                if "is_anomaly" in t_cols:
                    updates.append("is_anomaly = TRUE")
                vals.append(int(row[0]))
                cur.execute(
                    f"UPDATE transactions SET {', '.join(updates)} WHERE id = %s",
                    vals,
                )
        return inserted
    return 0


def seed_signup_ghost_workspace(
    cur: Any,
    user_id: int,
    profile: dict[str, Any],
    *,
    bank_label: str,
    display_name: str,
) -> dict[str, Any]:
    """
    Idempotent rich demo: EMI (varied per persona), 2 goals, festival, fraud (mixed types).
    Salary capped under ₹1L on users row.
    """
    ws = _workspace_for_profile(profile)
    income = _clamp_salary(float(profile.get("monthly_income", 50_000)))

    cur.execute(
        "UPDATE users SET monthly_income = %s, city = %s WHERE id = %s",
        (income, profile.get("city"), user_id),
    )

    stats: dict[str, Any] = {
        "monthly_income_inr": income,
        "emi_transactions": _seed_emi_transactions(
            cur, user_id, bank_label, display_name, ws.get("emis") or []
        ),
        "emis_rows": _seed_emis_table(cur, user_id, bank_label, ws.get("emis") or []),
        "purchase_goals": _seed_purchase_goals(cur, user_id, income, ws.get("goals") or []),
        "festival_budgets": _seed_festival(cur, user_id, ws.get("festival") or {}),
        "important_days": _seed_important_days(cur, user_id, ws.get("important_days") or []),
        "fraud_alerts": _seed_fraud_alerts(cur, user_id, ws.get("fraud") or []),
        "suspicious_txn": _seed_suspicious_transaction(
            cur, user_id, bank_label, ws.get("flag_txn"), ws.get("fraud") or []
        ),
    }
    stats["emi_count"] = len(ws.get("emis") or [])
    stats["fraud_count"] = len(ws.get("fraud") or [])
    stats["fraud_patterns"] = [f.get("pattern") for f in (ws.get("fraud") or [])]
    logger.info("signup_ghost_workspace user_id=%s stats=%s", user_id, stats)
    return stats
