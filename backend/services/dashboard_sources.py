"""Connected-source helpers: auto-merged mode when users link bank/UPI + card."""

from __future__ import annotations

from services.dashboard_scope import normalize_dashboard_mode

_BANKISH = frozenset({"bank", "bank_statement_pdf", "upi", "other"})


def count_distinct_visible_source_types(cur, user_id: int) -> int:
    cur.execute(
        """
        SELECT COUNT(DISTINCT cs.source_type)::int
        FROM connected_sources cs
        WHERE cs.user_id = %s
          AND COALESCE(cs.status, 'active') = 'active'
          AND COALESCE(cs.is_visible_on_dashboard, TRUE) = TRUE
        """,
        (user_id,),
    )
    return int((cur.fetchone() or [0])[0] or 0)


def user_has_multi_source_types(cur, user_id: int) -> bool:
    """True when more than one financial source type is active on the dashboard."""
    return count_distinct_visible_source_types(cur, user_id) >= 2


def user_has_bankish_and_card(cur, user_id: int) -> bool:
    cur.execute(
        """
        SELECT DISTINCT cs.source_type
        FROM connected_sources cs
        WHERE cs.user_id = %s
          AND COALESCE(cs.status, 'active') = 'active'
          AND COALESCE(cs.is_visible_on_dashboard, TRUE) = TRUE
        """,
        (user_id,),
    )
    types = {str(r[0] or "").strip().lower() for r in cur.fetchall()}
    has_card = "credit_card" in types
    has_bankish = bool(types & _BANKISH)
    return has_card and has_bankish


def ensure_merged_dashboard_if_multi_source(conn, user_id: int) -> bool:
    """
    When a user links UPI/bank + credit card (or 2+ source types), switch to merged
    and show every active source on the dashboard. Returns True if mode was updated.
    """
    cur = conn.cursor()
    try:
        if not user_has_multi_source_types(cur, user_id):
            return False
        cur.execute(
            """
            UPDATE users
            SET dashboard_mode = 'merged'
            WHERE id = %s
              AND COALESCE(dashboard_mode, 'merged') <> 'merged'
            """,
            (user_id,),
        )
        mode_changed = cur.rowcount > 0
        cur.execute(
            """
            UPDATE connected_sources
            SET is_visible_on_dashboard = TRUE
            WHERE user_id = %s AND COALESCE(status, 'active') = 'active'
            """,
            (user_id,),
        )
        return mode_changed or cur.rowcount > 0
    finally:
        cur.close()


def resolve_summary_scope_mode(cur, user_id: int, scope: str | None = None) -> str:
    """
    Scope used when persisting monthly_summary rows.
    Multi-source users always use merged so cached summaries match merged dashboards.
    """
    if scope is not None and str(scope).strip():
        return normalize_dashboard_mode(scope)
    if user_has_multi_source_types(cur, user_id):
        return "merged"
    cur.execute(
        "SELECT COALESCE(dashboard_mode, 'merged') FROM users WHERE id = %s",
        (user_id,),
    )
    row = cur.fetchone()
    return normalize_dashboard_mode(row[0] if row else "merged")
