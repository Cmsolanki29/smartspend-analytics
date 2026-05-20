#!/usr/bin/env python3
"""Audit May-2026 dashboard inflation for recent HDFC uploads; dedupe + resync summaries."""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import get_connection  # noqa: E402
from services.transaction_enrichment import sync_all_monthly_summaries_for_user  # noqa: E402


def _find_candidate_users(cur) -> list[tuple[int, str, str]]:
    cur.execute(
        """
        SELECT DISTINCT u.id, u.email, u.name
        FROM users u
        JOIN transactions t ON t.user_id = u.id
        JOIN connected_sources cs ON cs.id = t.connected_source_id AND cs.user_id = u.id
        WHERE LOWER(cs.institution_name) LIKE '%hdfc%'
          AND t.transaction_date >= '2026-05-01'
        ORDER BY u.id DESC
        LIMIT 20;
        """
    )
    return [(int(r[0]), str(r[1] or ""), str(r[2] or "")) for r in cur.fetchall()]


def audit_user(cur, user_id: int) -> dict:
    cur.execute(
        """
        SELECT COUNT(*)::bigint,
               COALESCE(SUM(CASE WHEN type='DEBIT' THEN amount ELSE 0 END), 0)::float,
               COALESCE(SUM(CASE WHEN type='CREDIT' THEN amount ELSE 0 END), 0)::float
        FROM transactions
        WHERE user_id = %s
          AND transaction_date >= '2026-05-01' AND transaction_date <= '2026-05-31';
        """,
        (user_id,),
    )
    may_cnt, may_deb, may_cred = cur.fetchone()

    cur.execute(
        """
        SELECT COUNT(*)::bigint FROM (
          SELECT transaction_date::date, ROUND(amount::numeric, 2), LEFT(COALESCE(description,''), 80)
          FROM transactions WHERE user_id = %s
          GROUP BY 1, 2, 3 HAVING COUNT(*) > 1
        ) d;
        """,
        (user_id,),
    )
    dup_groups = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT COALESCE(SUM(cnt - 1), 0)::bigint FROM (
          SELECT COUNT(*)::bigint AS cnt
          FROM transactions WHERE user_id = %s
          GROUP BY transaction_date::date, ROUND(amount::numeric, 2), LEFT(COALESCE(description,''), 80)
          HAVING COUNT(*) > 1
        ) x;
        """,
        (user_id,),
    )
    dup_extra_rows = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT year, month, total_income::float, total_expense::float, total_saved::float
        FROM monthly_summary
        WHERE user_id = %s AND year = 2026 AND month = 5;
        """,
        (user_id,),
    )
    ms = cur.fetchone()

    cur.execute(
        """
        SELECT COUNT(*)::int, COALESCE(SUM(rows_imported), 0)::int
        FROM uploaded_documents
        WHERE user_id = %s AND extraction_status = 'completed';
        """,
        (user_id,),
    )
    uploads = cur.fetchone()

    return {
        "may_txn_count": int(may_cnt or 0),
        "may_debits": float(may_deb or 0),
        "may_credits": float(may_cred or 0),
        "dup_groups": dup_groups,
        "dup_extra_rows": dup_extra_rows,
        "monthly_summary": ms,
        "completed_uploads": int(uploads[0] or 0),
        "rows_imported_total": int(uploads[1] or 0),
    }


def repair_running_balance_amounts(cur, user_id: int, opening: float = 118_000.0) -> int:
    """Fix rows where `amount` was stored as closing balance (PDF text parse bug)."""
    cur.execute(
        """
        SELECT id, transaction_date, type, amount::float, description
        FROM transactions
        WHERE user_id = %s
        ORDER BY transaction_date ASC, id ASC;
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return 0

    amts = [float(r[3]) for r in rows[:40]]
    if max(amts) < 80_000:
        return 0

    prev = opening
    updated = 0
    for tid, _d, _typ, bal, _desc in rows:
        bal = float(bal)
        if bal >= prev:
            true_amt, true_type = round(bal - prev, 2), "CREDIT"
        else:
            true_amt, true_type = round(prev - bal, 2), "DEBIT"
        if true_amt > 0:
            cur.execute(
                "UPDATE transactions SET amount = %s, type = %s WHERE id = %s AND user_id = %s;",
                (true_amt, true_type, tid, user_id),
            )
            updated += 1
        prev = bal
    return updated


def dedupe_user(cur, user_id: int) -> int:
    """Keep lowest id per (date, amount, description prefix); delete extras."""
    cur.execute(
        """
        WITH ranked AS (
          SELECT id,
                 ROW_NUMBER() OVER (
                   PARTITION BY transaction_date::date,
                                ROUND(amount::numeric, 2),
                                LEFT(COALESCE(description, ''), 80)
                   ORDER BY id ASC
                 ) AS rn
          FROM transactions
          WHERE user_id = %s
        )
        DELETE FROM transactions t
        USING ranked r
        WHERE t.id = r.id AND r.rn > 1
        RETURNING t.id;
        """,
        (user_id,),
    )
    deleted = cur.rowcount
    return int(deleted or 0)


def dump_may_rows(cur, user_id: int) -> None:
    cur.execute(
        """
        SELECT id, transaction_date, type, amount::float, LEFT(COALESCE(description,''), 70)
        FROM transactions
        WHERE user_id = %s AND transaction_date >= '2026-05-01' AND transaction_date <= '2026-05-31'
        ORDER BY amount DESC
        LIMIT 30;
        """,
        (user_id,),
    )
    print("  Top May 2026 rows:")
    for r in cur.fetchall():
        print(f"    {r}")

    cur.execute(
        """
        SELECT EXTRACT(YEAR FROM transaction_date)::int,
               EXTRACT(MONTH FROM transaction_date)::int,
               COUNT(*)::int,
               COALESCE(SUM(CASE WHEN type='DEBIT' THEN amount ELSE 0 END), 0)::float,
               COALESCE(SUM(CASE WHEN type='CREDIT' THEN amount ELSE 0 END), 0)::float
        FROM transactions WHERE user_id = %s
        GROUP BY 1, 2 ORDER BY 1, 2;
        """,
        (user_id,),
    )
    print("  By month:")
    for r in cur.fetchall():
        print(f"    {int(r[0])}-{int(r[1]):02d}: n={r[2]} deb={r[3]:,.0f} cred={r[4]:,.0f}")


def main() -> None:
    dry = "--apply" not in sys.argv
    user_arg = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--user=")), None)
    conn = get_connection()
    try:
        cur = conn.cursor()
        users = _find_candidate_users(cur)
        if not users:
            cur.execute(
                """
                SELECT u.id, u.email, u.name
                FROM users u
                ORDER BY u.id DESC
                LIMIT 5;
                """
            )
            users = [(int(r[0]), str(r[1] or ""), str(r[2] or "")) for r in cur.fetchall()]
            print("No HDFC May-2026 users; showing latest users:")

        targets = users
        if user_arg:
            cur.execute("SELECT id, email, name FROM users WHERE id = %s;", (user_arg,))
            row = cur.fetchone()
            targets = [(user_arg, str(row[1] or ""), str(row[2] or ""))] if row else []

        for uid, email, name in targets:
            a = audit_user(cur, uid)
            print(f"\n--- user_id={uid} {email} ({name}) ---")
            dump_may_rows(cur, uid)
            print(f"  May 2026 txns: {a['may_txn_count']} debits={a['may_debits']:,.2f} credits={a['may_credits']:,.2f}")
            print(f"  Duplicate groups: {a['dup_groups']} extra rows in dup groups: {a['dup_extra_rows']}")
            print(f"  monthly_summary May26: {a['monthly_summary']}")
            print(f"  completed uploads: {a['completed_uploads']} imported rows (sum): {a['rows_imported_total']}")

            if a["may_debits"] > 500_000 or a["dup_extra_rows"] > 0:
                target = uid
                print(f"  >>> candidate for fix: user_id={target}")
                if not dry:
                    fixed = repair_running_balance_amounts(cur, target)
                    print(f"  Repaired {fixed} transaction amounts (balance -> true debit/credit)")
                    n = dedupe_user(cur, target)
                    if n:
                        print(f"  Deleted {n} duplicate transaction rows")
                    synced = sync_all_monthly_summaries_for_user(conn, target)
                    conn.commit()
                    a2 = audit_user(cur, target)
                    print(f"  After fix May debits={a2['may_debits']:,.2f} credits={a2['may_credits']:,.2f}")
                    print(f"  Resynced {synced} monthly_summary month(s)")
                break
        else:
            print("\nNo user exceeded thresholds; pass --apply with a specific user_id if needed.")

        if dry:
            print("\nDry run only. Re-run with --apply to dedupe + resync.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
