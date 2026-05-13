#!/usr/bin/env python3
"""Assign corpus-backed transactions to an existing user (by email).

  cd backend
  python -m scripts.assign_user_transactions you@example.com
  python -m scripts.assign_user_transactions you@example.com --count 1400 --persona rahul_sw_blr
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
load_dotenv(_BACKEND.parent / ".env")
load_dotenv(_BACKEND / ".env")

from services.indian_fintech_seed.assign import assign_corpus_to_user  # noqa: E402


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
    p.add_argument("email", help="User email")
    p.add_argument("--count", type=int, default=0, help="Target txns (0 = random 1000-1500)")
    p.add_argument("--persona", type=str, default="", help="persona_key from user_personas")
    p.add_argument("--seed", type=int, default=None)
    args = p.parse_args(argv)
    email = (args.email or "").strip().lower()
    if "@" not in email:
        print("invalid email", file=sys.stderr)
        return 2

    cnt = args.count or random.randint(1000, 1500)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE lower(email) = lower(%s)", (email,))
            row = cur.fetchone()
            if not row:
                print("user not found", email, file=sys.stderr)
                return 3
            uid = int(row[0])
            n = assign_corpus_to_user(
                cur,
                uid,
                count=cnt,
                persona_key=args.persona.strip() or None,
                seed=args.seed,
            )
        conn.commit()
        print(f"OK user_id={uid} email={email} inserted_transactions={n} persona={args.persona or 'random'}")
        return 0
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print("FAILED", exc, file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
