"""Backfill synthetic transactions for an existing user (default: acs@gmail.com).

  cd backend
  python -m scripts.backfill_user_transactions
  python -m scripts.backfill_user_transactions you@example.com

Requires DB credentials in project root ``.env`` (same as ``apply_migrations``).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

_BACKEND = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND.parent / ".env")
load_dotenv(_BACKEND / ".env")


def _connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "smartspend_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("email", nargs="?", default="acs@gmail.com", help="User email (default: acs@gmail.com)")
    p.add_argument("--min", type=int, default=1100, dest="min_count", help="Minimum transaction rows (default: 1100)")
    args = p.parse_args(argv)
    email = (args.email or "").strip().lower()
    if not email or "@" not in email:
        print("Invalid email", file=sys.stderr)
        return 2

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE lower(email) = lower(%s)", (email,))
            row = cur.fetchone()
            if not row:
                print(f"No user found for email: {email}", file=sys.stderr)
                return 3
            uid = int(row[0])
            from services.demo_workspace_seed import seed_demo_workspace
            from services.new_user_transaction_seed import ensure_user_has_transactions

            added = ensure_user_has_transactions(cur, uid, min_count=args.min_count)
            demo_stats = seed_demo_workspace(cur, uid)
        conn.commit()
        print(
            f"OK user_id={uid} email={email} inserted_rows={added} (target min={args.min_count}) "
            f"demo_workspace={demo_stats}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
