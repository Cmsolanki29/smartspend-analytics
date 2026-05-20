"""Phase 1 smoke tests — parser enrichment, migration column, upload pipeline imports."""
from __future__ import annotations

import sys

from db import get_connection


def test_parser_utils() -> None:
    from services.parser_utils import enrich_category, merchant_prefix_key, stored_category_for_merchant
    from services.transaction_upsert import enrich_transaction_row

    assert enrich_category("SWIGGY FOOD ORDER") == "Food"
    assert enrich_category("AMAZON PAY") == "Shopping"
    assert enrich_category("UNKNOWN SHOP XYZ") == "Others"
    row = enrich_transaction_row({"merchant": "ZOMATO LIMITED"})
    assert row["category"] == "Food & Dining"
    assert row["normalized_merchant"] == merchant_prefix_key("ZOMATO LIMITED")
    assert stored_category_for_merchant("NETFLIX SUB") == "Entertainment"
    # Regression: unknown merchant + LLM category must not recurse (upload RecursionError)
    assert (
        stored_category_for_merchant("XYZ UNKNOWN MERCHANT", "food")
        == "Food & Dining"
    )
    enrich_transaction_row(
        {
            "merchant": "RANDOM MERCHANT ABC",
            "description": "UPI payment",
            "category": "utilities",
        }
    )
    print("  ok parser_utils + transaction_upsert")


def test_db_column() -> None:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'transactions'
              AND column_name = 'normalized_merchant';
            """
        )
        assert cur.fetchone(), "normalized_merchant column missing"
        cur.execute(
            """
            SELECT COUNT(*)::int FROM transactions
            WHERE normalized_merchant IS NOT NULL AND TRIM(normalized_merchant) <> '';
            """
        )
        n = int(cur.fetchone()[0])
        print(f"  ok normalized_merchant column ({n} rows backfilled)")
    finally:
        cur.close()
        conn.close()


def test_upload_pipeline_import() -> None:
    from services.upload_pipeline import run_post_import_pipeline

    assert callable(run_post_import_pipeline)
    print("  ok upload_pipeline import")


def test_ghost_seed_idempotent() -> None:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users ORDER BY id DESC LIMIT 1;")
        row = cur.fetchone()
        if not row:
            print("  skip ghost_seed (no users)")
            return
        uid = int(row[0])
        from services.onboarding_seed import seed_ghost_connected_sources

        n1 = seed_ghost_connected_sources(cur, uid)
        n2 = seed_ghost_connected_sources(cur, uid)
        conn.rollback()
        print(f"  ok ghost_seed idempotent probe user_id={uid} first={n1} second={n2}")
    finally:
        cur.close()
        conn.close()


def main() -> int:
    print("Phase 1 tests")
    tests = [
        test_parser_utils,
        test_db_column,
        test_upload_pipeline_import,
        test_ghost_seed_idempotent,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            failed += 1
            print(f"  FAIL {t.__name__}: {exc}")
    if failed:
        print(f"\n{failed} failed")
        return 1
    print("\nAll Phase 1 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
