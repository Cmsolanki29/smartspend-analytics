"""Filter transactions by users.dashboard_mode + connected_sources visibility."""

from __future__ import annotations

_VALID_MODES = frozenset({"merged", "bank_only", "credit_card_only"})


def normalize_dashboard_mode(mode: str | None) -> str:
    m = (mode or "merged").strip().lower()
    return m if m in _VALID_MODES else "merged"


def transaction_scope_sql(table_alias: str, mode: str | None) -> str:
    """
    SQL boolean expression (no bind params) for rows in ``table_alias`` that count
    toward the user's dashboard for the given mode.

    - merged: seed/unlinked (NULL source) OR linked rows whose source is visible.
    - bank_only: NULL source OR visible bank / statement / UPI / other (not credit_card).
    - credit_card_only: only visible credit_card rows (excludes NULL source demo bank).
    """
    a = table_alias
    m = normalize_dashboard_mode(mode)

    visible = f"""EXISTS (
      SELECT 1 FROM connected_sources cs
      WHERE cs.id = {a}.connected_source_id
        AND cs.user_id = {a}.user_id
        AND COALESCE(cs.is_visible_on_dashboard, TRUE)
        AND COALESCE(cs.status, 'active') = 'active'
    )"""

    if m == "credit_card_only":
        return f"""(
          {a}.connected_source_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM connected_sources cs
            WHERE cs.id = {a}.connected_source_id
              AND cs.user_id = {a}.user_id
              AND cs.source_type = 'credit_card'
              AND COALESCE(cs.is_visible_on_dashboard, TRUE)
              AND COALESCE(cs.status, 'active') = 'active'
          )
        )"""

    if m == "bank_only":
        return f"""(
          {a}.connected_source_id IS NULL
          OR EXISTS (
            SELECT 1 FROM connected_sources cs
            WHERE cs.id = {a}.connected_source_id
              AND cs.user_id = {a}.user_id
              AND cs.source_type IN ('bank', 'bank_statement_pdf', 'upi', 'other')
              AND COALESCE(cs.is_visible_on_dashboard, TRUE)
              AND COALESCE(cs.status, 'active') = 'active'
          )
        )"""

    # merged
    return f"""(
      {a}.connected_source_id IS NULL
      OR {visible}
    )"""


def fetch_dashboard_mode(cur, user_id: int) -> str:
    cur.execute(
        "SELECT COALESCE(dashboard_mode, 'merged') FROM users WHERE id = %s",
        (user_id,),
    )
    row = cur.fetchone()
    return normalize_dashboard_mode(row[0] if row else "merged")
