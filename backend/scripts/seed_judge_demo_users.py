#!/usr/bin/env python3
"""
Create 6 fixed login accounts with realistic data (1100+ txns + demo_workspace).

  cd backend
  python -m scripts.seed_judge_demo_users

Password for ALL accounts: Pass@123

Emails use ``@judge.smartspend.example.com`` (IANA example domain; passes strict
email-validator everywhere). Legacy ``@demo.smartspend.local`` rows are renamed on run.

Idempotent: re-run resets transactions + demo rows for these users only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
load_dotenv(_BACKEND.parent / ".env")
load_dotenv(_BACKEND / ".env")

from datetime import date  # noqa: E402

from services.demo_workspace_seed import seed_demo_workspace  # noqa: E402
from services.new_user_transaction_seed import ensure_user_has_transactions  # noqa: E402
from utils.auth import hash_password  # noqa: E402

# Shared password (meets signup rules; bcrypt via app hasher)
DEMO_PASSWORD = "Pass@123"

JUDGE_EMAIL_DOMAIN = "judge.smartspend.example.com"
LEGACY_JUDGE_DOMAIN = "demo.smartspend.local"

# (email, display_name, monthly_income)
DEMO_USERS: tuple[tuple[str, str, float], ...] = (
    ("judgedemo1@judge.smartspend.example.com", "Priya Kulkarni", 88_000.0),
    # Rahul: 110k income → DTI ~27.5% (Watch). Phone/Scooty EMI shortfall ~₹248,
    # closeable by deferring "Family weekend trip" to Holi → clean end-to-end demo flow.
    ("judgedemo2@judge.smartspend.example.com", "Rahul Mehta", 110_000.0),
    ("judgedemo3@judge.smartspend.example.com", "Ananya Desai", 95_000.0),
    ("judgedemo4@judge.smartspend.example.com", "Vikram Singh", 68_000.0),
    ("judgedemo5@judge.smartspend.example.com", "Neha Joshi", 110_000.0),
    ("judgedemo6@judge.smartspend.example.com", "Karan Ahuja", 54_000.0),
)


def _connect():
    from utils.pg_connect import connect

    return connect()


def main() -> int:
    ph = hash_password(DEMO_PASSWORD)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            for i in range(1, 7):
                cur.execute(
                    """
                    UPDATE users SET email = %s
                    WHERE lower(email) = lower(%s);
                    """,
                    (
                        f"judgedemo{i}@{JUDGE_EMAIL_DOMAIN}",
                        f"judgedemo{i}@{LEGACY_JUDGE_DOMAIN}",
                    ),
                )
            for email, name, income in DEMO_USERS:
                email = email.lower().strip()
                cur.execute(
                    """
                    INSERT INTO users (
                      name, email, password_hash, monthly_income,
                      onboarding_completed, is_verified
                    ) VALUES (%s, %s, %s, %s, TRUE, TRUE)
                    ON CONFLICT (email) DO UPDATE SET
                      name = EXCLUDED.name,
                      password_hash = EXCLUDED.password_hash,
                      monthly_income = EXCLUDED.monthly_income,
                      onboarding_completed = TRUE,
                      is_verified = TRUE
                    RETURNING id;
                    """,
                    (name, email, ph, income),
                )
                row = cur.fetchone()
                uid = int(row[0])
                cur.execute("DELETE FROM fraud_alerts WHERE user_id = %s;", (uid,))
                cur.execute(
                    "DELETE FROM fraud_alerts WHERE transaction_id IN (SELECT id FROM transactions WHERE user_id = %s);",
                    (uid,),
                )
                cur.execute("DELETE FROM alerts WHERE user_id = %s;", (uid,))
                cur.execute("DELETE FROM dark_patterns WHERE user_id = %s;", (uid,))
                cur.execute("DELETE FROM transactions WHERE user_id = %s;", (uid,))
                cur.execute("DELETE FROM monthly_summary WHERE user_id = %s;", (uid,))
                cur.execute("DELETE FROM purchase_goals WHERE user_id = %s;", (uid,))
                cur.execute("DELETE FROM festival_budgets WHERE user_id = %s;", (uid,))
                cur.execute("DELETE FROM user_important_days WHERE user_id = %s;", (uid,))
                ensure_user_has_transactions(cur, uid, min_count=1100, anchor_date=date.today())
                seed_demo_workspace(cur, uid)
                cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id = %s;", (uid,))
                ntx = int(cur.fetchone()[0] or 0)
                print(f"OK user_id={uid} email={email} txns={ntx} name={name}")
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print("FAILED:", exc, file=sys.stderr)
        return 1
    finally:
        conn.close()

    print()
    print("=== LOGIN (all same password) ===")
    print(f"Password: {DEMO_PASSWORD}")
    for email, name, _ in DEMO_USERS:
        print(f"  {email}")
    print()
    print("Open http://localhost:3000 -> Sign in (not sign up) with any email above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
