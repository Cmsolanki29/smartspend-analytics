"""
Shared transaction ledger rollups for Health Score + Dashboard KPIs.

Single source of truth: scoped rows in `transactions` (same filters as dashboard).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from services.dashboard_scope import fetch_dashboard_mode, normalize_dashboard_mode, transaction_scope_sql

# Match dashboard merged-view intent: exclude internal card payments from spend.
_DEBIT_SPEND_FILTER = """
    t.type = 'DEBIT'
    AND COALESCE(t.category, '') <> 'internal_transfer'
"""


def _month_bounds(month: int, year: int) -> tuple[date, date]:
    dim = __import__("calendar").monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, dim)


def fetch_ledger_summary(
    cur,
    user_id: int,
    month: int,
    year: int,
    scope: str | None = None,
) -> dict[str, Any]:
    """
    Month + YTD metrics from transactions for the user's dashboard scope.
    """
    mode = (
        normalize_dashboard_mode(scope)
        if scope is not None
        else fetch_dashboard_mode(cur, user_id)
    )
    scope_sql = transaction_scope_sql("t", mode)
    month_start, month_end = _month_bounds(month, year)
    ytd_start = date(year, 1, 1)
    ytd_end = date(year, 12, 31)

    cur.execute(
        "SELECT COALESCE(monthly_income, 0)::float FROM users WHERE id = %s;",
        (user_id,),
    )
    profile_income = float((cur.fetchone() or [0])[0] or 0)

    cur.execute(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN t.type = 'CREDIT' THEN t.amount ELSE 0 END), 0)::float,
            COALESCE(SUM(CASE WHEN {_DEBIT_SPEND_FILTER} THEN t.amount ELSE 0 END), 0)::float,
            COALESCE(SUM(CASE WHEN t.type = 'DEBIT' THEN t.amount ELSE 0 END), 0)::float
        FROM transactions t
        WHERE t.user_id = %s
          AND t.transaction_date >= %s
          AND t.transaction_date <= %s
          AND ({scope_sql});
        """,
        (user_id, month_start, month_end),
    )
    inc_m, exp_spend_m, exp_all_m = cur.fetchone() or (0, 0, 0)
    month_credits = float(inc_m or 0)
    month_debit_spend = float(exp_spend_m or 0)
    month_debit_all = float(exp_all_m or 0)
    month_net = round(month_credits - month_debit_all, 2)
    month_saved_display = round(month_credits - month_debit_spend, 2)
    savings_rate = (
        round(month_saved_display / month_credits * 100, 2) if month_credits > 0 else 0.0
    )

    cur.execute(
        f"""
        WITH monthly AS (
            SELECT
                EXTRACT(MONTH FROM t.transaction_date)::int AS m,
                COALESCE(SUM(CASE WHEN t.type = 'CREDIT' THEN t.amount ELSE 0 END), 0)::float AS inc,
                COALESCE(SUM(CASE WHEN {_DEBIT_SPEND_FILTER} THEN t.amount ELSE 0 END), 0)::float AS exp
            FROM transactions t
            WHERE t.user_id = %s
              AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
              AND t.transaction_date >= %s
              AND t.transaction_date <= %s
              AND ({scope_sql})
            GROUP BY 1
        )
        SELECT COALESCE(SUM(GREATEST(0, inc - exp)), 0)::float FROM monthly;
        """,
        (user_id, year, ytd_start, ytd_end),
    )
    ytd_saved = round(float((cur.fetchone() or [0])[0] or 0), 2)

    cur.execute(
        f"""
        SELECT COUNT(*)::int
        FROM transactions t
        WHERE t.user_id = %s AND t.anomaly_flag = TRUE
          AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
          AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
          AND ({scope_sql});
        """,
        (user_id, month, year),
    )
    anomaly_count = int((cur.fetchone() or [0])[0] or 0)

    cur.execute(
        f"""
        SELECT COUNT(DISTINCT COALESCE(t.category, 'Uncategorized'))::int
        FROM transactions t
        WHERE t.user_id = %s AND {_DEBIT_SPEND_FILTER}
          AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
          AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
          AND ({scope_sql});
        """,
        (user_id, month, year),
    )
    distinct_categories = int((cur.fetchone() or [0])[0] or 0)

    cur.execute(
        f"""
        SELECT COUNT(*)::int, COUNT(DISTINCT t.transaction_date::date)::int
        FROM transactions t
        WHERE t.user_id = %s
          AND t.transaction_date >= (CURRENT_DATE - INTERVAL '90 days')
          AND ({scope_sql});
        """,
        (user_id,),
    )
    txn_row = cur.fetchone() or (0, 0)
    txn_count_90d = int(txn_row[0] or 0)
    distinct_days_90d = int(txn_row[1] or 0)

    income_basis = max(month_credits, profile_income)

    return {
        "scope_mode": mode,
        "month": month,
        "year": year,
        "profile_income_inr": round(profile_income, 2),
        "month_credits_inr": round(month_credits, 2),
        "month_debit_spend_inr": round(month_debit_spend, 2),
        "month_debit_all_inr": round(month_debit_all, 2),
        "month_net_inr": month_net,
        "month_saved_display_inr": month_saved_display,
        "savings_rate_pct": savings_rate,
        "ytd_saved_inr": ytd_saved,
        "income_basis_inr": round(income_basis, 2),
        "anomaly_count": anomaly_count,
        "distinct_categories": distinct_categories,
        "txn_count_90d": txn_count_90d,
        "distinct_days_90d": distinct_days_90d,
        "has_enough_data": txn_count_90d >= 10,
    }


def persist_monthly_summary_row(
    conn,
    user_id: int,
    month: int,
    year: int,
    ledger: dict[str, Any],
    *,
    health_score: int | None,
    anomaly_count: int,
) -> None:
    """Keep monthly_summary aligned with ledger + live health score."""
    if health_score is None:
        return
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE monthly_summary SET
                total_income = %s,
                total_expense = %s,
                total_saved = %s,
                savings_rate = %s,
                health_score = %s,
                anomaly_count = %s
            WHERE user_id = %s AND month = %s AND year = %s;
            """,
            (
                float(ledger.get("month_credits_inr") or 0),
                float(ledger.get("month_debit_spend_inr") or 0),
                float(ledger.get("month_saved_display_inr") or 0),
                float(ledger.get("savings_rate_pct") or 0),
                int(health_score),
                int(anomaly_count),
                user_id,
                month,
                year,
            ),
        )
        if cur.rowcount == 0:
            cur.execute(
                """
                INSERT INTO monthly_summary (
                    user_id, month, year, total_income, total_expense, total_saved,
                    savings_rate, health_score, anomaly_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    user_id,
                    month,
                    year,
                    float(ledger.get("month_credits_inr") or 0),
                    float(ledger.get("month_debit_spend_inr") or 0),
                    float(ledger.get("month_saved_display_inr") or 0),
                    float(ledger.get("savings_rate_pct") or 0),
                    int(health_score),
                    int(anomaly_count),
                ),
            )
    except Exception:
        pass
    finally:
        cur.close()
