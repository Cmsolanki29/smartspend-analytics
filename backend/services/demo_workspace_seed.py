"""Idempotent demo data: EMI-like debits, subscriptions, goals, fraud, festivals, summaries."""

from __future__ import annotations

import calendar
import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from services.new_user_transaction_seed import insert_individual_transactions

logger = logging.getLogger(__name__)

DEMO_MONTHLY_INCOME = 95_000.0


def _cols(cur: Any, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return {str(r[0]) for r in cur.fetchall()}


def _month_dates_clamped(today: date, n_months: int, day_of_month: int) -> list[date]:
    """Chronological list of dates in the last ``n_months`` calendar months (ending at ``today``'s month)."""
    out: list[date] = []
    y, m = today.year, today.month
    for i in range(n_months - 1, -1, -1):
        yy, mm = y, m - i
        while mm < 1:
            mm += 12
            yy -= 1
        dim = calendar.monthrange(yy, mm)[1]
        out.append(date(yy, mm, min(day_of_month, dim)))
    return out


def _txn_count_like(cur: Any, user_id: int, needle: str) -> int:
    cur.execute(
        """
        SELECT COUNT(*) FROM transactions
        WHERE user_id = %s AND transaction_date >= (CURRENT_DATE - INTERVAL '8 months')
          AND (LOWER(COALESCE(merchant,'')) LIKE %s OR LOWER(COALESCE(description,'')) LIKE %s)
        """,
        (user_id, f"%{needle}%", f"%{needle}%"),
    )
    return int(cur.fetchone()[0] or 0)


def seed_demo_workspace(cur: Any, user_id: int) -> dict[str, int]:
    """
    Add realistic rows for EMI Tracker, Subscriptions, Purchase Planner, FraudShield,
    Festival widgets, anomaly alerts, and ``monthly_summary`` — safe to call repeatedly.
    """
    stats: dict[str, int] = {}

    cur.execute("SELECT 1 FROM users WHERE id = %s;", (user_id,))
    if not cur.fetchone():
        logger.warning("seed_demo_workspace: no user id=%s", user_id)
        return stats

    cur.execute(
        "UPDATE users SET monthly_income = %s WHERE id = %s AND (monthly_income IS NULL OR monthly_income <= 0);",
        (DEMO_MONTHLY_INCOME, user_id),
    )
    stats["users_income_touched"] = int(cur.rowcount or 0)

    today = date.today()
    tx_specs: list[dict[str, Any]] = []

    if _txn_count_like(cur, user_id, "hdfc home loan emi") < 3:
        for d in _month_dates_clamped(today, 4, 5):
            tx_specs.append(
                {
                    "transaction_date": d,
                    "amount": 18_999.0,
                    "merchant": "HDFC Home Loan EMI",
                    "category": "Finance",
                    "type": "DEBIT",
                    "description": "Home loan EMI repayment NACH HDFC Ltd",
                }
            )
        stats["emi_hdfc_txns"] = 4

    if _txn_count_like(cur, user_id, "icici bank personal loan") < 3:
        for d in _month_dates_clamped(today, 4, 18):
            tx_specs.append(
                {
                    "transaction_date": d,
                    "amount": 11_249.0,
                    "merchant": "ICICI Bank Personal Loan",
                    "category": "Finance",
                    "type": "DEBIT",
                    "description": "Personal loan EMI ECS repayment",
                }
            )
        stats["emi_icici_txns"] = 4

    if _txn_count_like(cur, user_id, "netflix") < 4:
        base = today - timedelta(days=95)
        for i, amt in enumerate((499.0, 499.0, 499.0, 499.0)):
            tx_specs.append(
                {
                    "transaction_date": base + timedelta(days=i * 30),
                    "amount": amt,
                    "merchant": "Netflix India",
                    "category": "Entertainment",
                    "type": "DEBIT",
                    "description": "Netflix monthly subscription UPI",
                }
            )
        stats["sub_netflix_txns"] = 4

    if _txn_count_like(cur, user_id, "spotify") < 4:
        base = today - timedelta(days=88)
        for i in range(4):
            tx_specs.append(
                {
                    "transaction_date": base + timedelta(days=i * 31),
                    "amount": 299.0,
                    "merchant": "Spotify India",
                    "category": "Entertainment",
                    "type": "DEBIT",
                    "description": "Spotify Premium plan renewal",
                }
            )
        stats["sub_spotify_txns"] = 4

    if _txn_count_like(cur, user_id, "securevpn") < 2:
        tx_specs.append(
            {
                "transaction_date": today - timedelta(days=38),
                "amount": 3.0,
                "merchant": "SecureVPN Pro Trial",
                "category": "Entertainment",
                "type": "DEBIT",
                "description": "VPN trial activation charge",
            }
        )
        tx_specs.append(
            {
                "transaction_date": today - timedelta(days=12),
                "amount": 499.0,
                "merchant": "SecureVPN Pro Trial",
                "category": "Entertainment",
                "type": "DEBIT",
                "description": "VPN premium renewal after trial",
            }
        )
        stats["dark_pattern_vpn_txns"] = 2

    if _txn_count_like(cur, user_id, "salary credit") < 3:
        for d in _month_dates_clamped(today, 3, 1):
            tx_specs.append(
                {
                    "transaction_date": d,
                    "amount": 92_000.0,
                    "merchant": "Employer Payroll",
                    "category": "Salary",
                    "type": "CREDIT",
                    "description": "Monthly salary credit NEFT",
                }
            )
        stats["salary_credits"] = 3

    if tx_specs:
        inserted = insert_individual_transactions(cur, user_id, tx_specs)
        stats["pattern_transactions_inserted"] = inserted

    cur.execute(
        """
        SELECT COUNT(*) FROM purchase_goals
        WHERE user_id = %s AND UPPER(COALESCE(status, '')) <> 'CANCELLED';
        """,
        (user_id,),
    )
    if int(cur.fetchone()[0] or 0) < 2:
        td1 = today + timedelta(days=150)   # Laptop: ~5 months away (Diwali-ish)
        td2 = today + timedelta(days=240)   # Family trip: ~8 months away
        sv1 = round(85_000.0 * 0.12, 2)    # 12% saved for laptop
        sv2 = round(42_000.0 * 0.12, 2)    # 12% saved for trip
        # monthly_target = remaining / months_left (realistic recalculation)
        m1 = max((td1 - today).days / 30.0, 1.0)
        m2 = max((td2 - today).days / 30.0, 1.0)
        mt1 = round((85_000.0 - sv1) / m1, 2)
        mt2 = round((42_000.0 - sv2) / m2, 2)
        for item_name, target, saved, td, mt, cat, priority, buy_window in (
            # Laptop is festival/deadline-driven → HIGH
            ("Laptop upgrade (Diwali)", 85_000.0, sv1, td1, mt1, "ELECTRONICS", "HIGH", "Oct 2026 — pre-festival pricing"),
            # Weekend trip is a lifestyle goal → MEDIUM (can be deferred if EMI pressure rises)
            ("Family weekend trip", 42_000.0, sv2, td2, mt2, "TRAVEL", "MEDIUM", "Jan 2027 — New-year clearance"),
        ):
            cur.execute(
                """
                INSERT INTO purchase_goals (
                  user_id, item_name, target_amount, saved_amount, target_date, monthly_target,
                  category, priority, status, best_buy_month, emi_vs_cash, sacrifice_plan
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'SAVING', %s, '{}'::jsonb, '{}'::jsonb);
                """,
                (user_id, item_name, target, saved, td, mt, cat, priority, buy_window),
            )
        stats["purchase_goals_inserted"] = 2

    cur.execute(
        """
        SELECT COUNT(*) FROM festival_budgets
        WHERE user_id = %s AND EXTRACT(YEAR FROM festival_date)::int = 2026;
        """,
        (user_id,),
    )
    if int(cur.fetchone()[0] or 0) < 1:
        diwali = date(2026, 10, 20)
        days_rem = max((diwali - today).days, 1)
        months_rem = max(days_rem / 30.0, 0.25)
        planned = 35_000.0
        monthly_needed = planned / months_rem
        cur.execute(
            """
            INSERT INTO festival_budgets (
              user_id, festival_name, festival_date, last_year_spent, planned_budget,
              saved_so_far, monthly_target, days_remaining, status, category_breakdown
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'UPCOMING', %s::jsonb);
            """,
            (
                user_id,
                "Diwali",
                diwali,
                28_000.0,
                planned,
                8_000.0,
                round(monthly_needed, 2),
                days_rem,
                json.dumps({"Gifts": 12000, "Shopping": 15000, "Food": 8000}),
            ),
        )
        stats["festival_budgets_inserted"] = 1

    cur.execute("SELECT COUNT(*) FROM user_important_days WHERE user_id = %s;", (user_id,))
    if int(cur.fetchone()[0] or 0) < 2:
        cur.execute(
            """
            INSERT INTO user_important_days (user_id, title, event_date, notes, repeats_yearly)
            VALUES
              (%s, %s, %s, %s, FALSE),
              (%s, %s, %s, %s, TRUE);
            """,
            (
                user_id,
                "Parent anniversary dinner",
                today + timedelta(days=40),
                "Book table 2 weeks ahead",
                user_id,
                "Spouse birthday",
                date(today.year, 12, 18) if today <= date(today.year, 12, 17) else date(today.year + 1, 12, 18),
                "Gift + cake budget in Purchase Planner",
            ),
        )
        stats["important_days_inserted"] = 2

    cur.execute("SELECT COUNT(*) FROM fraud_alerts WHERE user_id = %s;", (user_id,))
    fa_existing = int(cur.fetchone()[0] or 0)
    if fa_existing < 2:
        cur.execute("SELECT id FROM transactions WHERE user_id = %s ORDER BY id DESC LIMIT 1;", (user_id,))
        row = cur.fetchone()
        txn_id = int(row[0]) if row else None
        alert_cols = _cols(cur, "fraud_alerts")
        if txn_id and alert_cols:
            for pattern, score, amt, sev in (
                ("UPI_MULE_TRANSFER", 72, 18_500.0, "HIGH"),
                ("CARD_TEST_MICROCHARGES", 58, 3_200.0, "MEDIUM"),
            ):
                av: dict[str, Any] = {"user_id": user_id, "transaction_id": txn_id, "risk_score": score}
                if "pattern_matched" in alert_cols:
                    av["pattern_matched"] = pattern
                if "amount_at_risk" in alert_cols:
                    av["amount_at_risk"] = amt
                if "warning_message" in alert_cols:
                    av["warning_message"] = f"Demo alert — review Rs {amt:,.0f} pattern ({pattern})"
                if "hinglish_explanation" in alert_cols:
                    av["hinglish_explanation"] = "Demo seed — FraudShield UI check."
                if "user_action" in alert_cols:
                    av["user_action"] = "PENDING"
                if "money_saved" in alert_cols:
                    av["money_saved"] = 0.0
                if "severity" in alert_cols:
                    av["severity"] = sev
                if "created_at" in alert_cols:
                    av["created_at"] = datetime.now(timezone.utc) - timedelta(days=2)
                keys = list(av.keys())
                cur.execute(
                    f"INSERT INTO fraud_alerts ({', '.join(keys)}) VALUES ({', '.join(['%s'] * len(keys))})",
                    [av[k] for k in keys],
                )
            stats["fraud_alerts_inserted"] = 2

    cur.execute(
        "SELECT COUNT(*) FROM alerts WHERE user_id = %s AND is_read = FALSE;",
        (user_id,),
    )
    unread = int(cur.fetchone()[0] or 0)
    if unread < 2:
        cur.execute("SELECT id FROM transactions WHERE user_id = %s ORDER BY id DESC LIMIT 1;", (user_id,))
        row = cur.fetchone()
        txn_id = int(row[0]) if row else None
        alert_cols = _cols(cur, "alerts")
        if txn_id and alert_cols:
            now = datetime.now(timezone.utc)
            for sev, atype, msg in (
                ("MEDIUM", "VELOCITY_SPIKE", "Demo: spending velocity up vs your 90-day baseline."),
                ("LOW", "CATEGORY_SHIFT", "Demo: Food delivery share increased this week."),
            ):
                cols_ins = ["user_id", "severity", "alert_type", "message"]
                vals = [user_id, sev, atype, msg]
                if "transaction_id" in alert_cols:
                    cols_ins.append("transaction_id")
                    vals.append(txn_id)
                if "detail" in alert_cols:
                    cols_ins.append("detail")
                    vals.append("Seeded by demo_workspace_seed for QA.")
                if "is_read" in alert_cols:
                    cols_ins.append("is_read")
                    vals.append(False)
                if "created_at" in alert_cols:
                    cols_ins.append("created_at")
                    vals.append(now)
                ph = ", ".join(["%s"] * len(vals))
                cur.execute(
                    f"INSERT INTO alerts ({', '.join(cols_ins)}) VALUES ({ph})",
                    vals,
                )
            stats["anomaly_alerts_inserted"] = 2

    ms_cols = _cols(cur, "monthly_summary")
    if ms_cols and "user_id" in ms_cols and "month" in ms_cols and "year" in ms_cols:
        y, m = today.year, today.month
        inc = 92_000.0
        exp = 61_000.0
        saved = max(0.0, inc - exp)
        sr = round((saved / inc) * 100, 2) if inc else 0.0
        hs = 74
        row_vals: dict[str, Any] = {
            "user_id": user_id,
            "year": y,
            "month": m,
            "total_income": inc,
            "total_expense": exp,
            "total_saved": saved,
            "savings_rate": sr,
            "health_score": hs,
            "anomaly_count": 1,
            "high_risk_count": 0,
        }
        if "category_breakdown" in ms_cols:
            row_vals["category_breakdown"] = json.dumps({"Food": 12000, "Shopping": 9000, "Finance": 30500})
        if "computed_at" in ms_cols:
            row_vals["computed_at"] = datetime.now(timezone.utc)
        keys = [k for k in row_vals if k in ms_cols]
        vals = [row_vals[k] for k in keys]
        updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in keys if k not in ("user_id", "year", "month"))
        cur.execute(
            f"""
            INSERT INTO monthly_summary ({", ".join(keys)})
            VALUES ({", ".join(["%s"] * len(keys))})
            ON CONFLICT (user_id, month, year) DO UPDATE SET {updates};
            """,
            vals,
        )
        stats["monthly_summary_upserted"] = 1

    logger.info("seed_demo_workspace user_id=%s stats=%s", user_id, stats)
    return stats
