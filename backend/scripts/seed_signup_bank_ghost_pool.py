#!/usr/bin/env python3
"""Seed all seven signup bank ghost pools (900001–900007)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import get_connection  # noqa: E402
from services.signup_bank_ghost_pool import (  # noqa: E402
    SIGNUP_GHOST_PROFILES,
    ensure_signup_ghost_pool_seeded,
    ghost_pool_summary,
)


def main() -> None:
    conn = get_connection()
    cur = conn.cursor()
    try:
        total = ensure_signup_ghost_pool_seeded(cur)
        conn.commit()
        print(f"Seeded/verified ghost pool rows generated this run: {total}")
        print(f"Profiles: {len(SIGNUP_GHOST_PROFILES)}")
        for row in ghost_pool_summary():
            cur.execute(
                "SELECT COUNT(*) FROM transactions WHERE user_id = %s",
                (row["pool_user_id"],),
            )
            cnt = int(cur.fetchone()[0])
            print(
                f"  {row['bank']:5} id={row['pool_user_id']} "
                f"{row['persona']:18} {row['city']:12} txns={cnt}"
            )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
