"""Per-user onboarding placeholders — scoped by user_id only."""

from __future__ import annotations

GHOST_BANK_SOURCES: tuple[tuple[str, str], ...] = (
    ("HDFC Bank", "bank"),
    ("State Bank of India", "bank"),
    ("ICICI Bank", "bank"),
    ("Axis Bank", "bank"),
    ("Kotak Mahindra", "bank"),
)


def _seed_ghost_rows(cur, user_id: int, *, with_ghost_flag: bool) -> int:
    inserted = 0
    for institution, source_type in GHOST_BANK_SOURCES:
        if with_ghost_flag:
            cur.execute(
                """
                INSERT INTO connected_sources (
                  user_id, source_type, institution_name, account_number_masked,
                  is_primary, is_visible_on_dashboard, added_via, status, is_ghost
                )
                SELECT %s, %s, %s, 'Ghost', FALSE, FALSE, 'ghost_seed', 'inactive', TRUE
                WHERE NOT EXISTS (
                  SELECT 1 FROM connected_sources
                  WHERE user_id = %s
                    AND institution_name = %s
                    AND source_type = %s
                    AND COALESCE(is_ghost, FALSE) = TRUE
                );
                """,
                (user_id, source_type, institution, user_id, institution, source_type),
            )
        else:
            cur.execute(
                """
                INSERT INTO connected_sources (
                  user_id, source_type, institution_name, account_number_masked,
                  is_primary, is_visible_on_dashboard, added_via, status
                )
                SELECT %s, %s, %s, 'Ghost', FALSE, FALSE, 'ghost_seed', 'inactive'
                WHERE NOT EXISTS (
                  SELECT 1 FROM connected_sources
                  WHERE user_id = %s
                    AND institution_name = %s
                    AND source_type = %s
                    AND added_via = 'ghost_seed'
                );
                """,
                (user_id, source_type, institution, user_id, institution, source_type),
            )
        inserted += int(cur.rowcount or 0)
    return inserted


def seed_ghost_connected_sources(cur, user_id: int) -> int:
    """Insert invisible placeholder sources for bank-picker UI (per user_id)."""
    try:
        return _seed_ghost_rows(cur, user_id, with_ghost_flag=True)
    except Exception as exc:  # noqa: BLE001
        if "is_ghost" not in str(exc).lower():
            raise
        return _seed_ghost_rows(cur, user_id, with_ghost_flag=False)
