"""Single formula for cancellation savings — used in verdicts, cards, and dashboard."""
from __future__ import annotations

from typing import Any

from psycopg2.extensions import connection as PgConnection

from services.subscription_intelligence.linked_apps import fetch_linked_packages


def usage_hours_from_minutes(usage_minutes: float) -> float:
    return max(0.0, float(usage_minutes or 0)) / 60.0


def estimate_cancellation_savings_inr(monthly_cost: float, usage_hours_30d: float) -> float:
    """
    Recoverable INR/month if user cancels.
    - Under 2h / 30d (barely used): full subscription cost.
    - Otherwise (declining but some use): 70% of cost (conservative recoverable spend).
    """
    cost = max(0.0, float(monthly_cost or 0))
    hours = max(0.0, float(usage_hours_30d or 0))
    if cost <= 0:
        return 0.0
    if hours < 2.0:
        return round(cost, 2)
    return round(cost * 0.7, 2)


def display_savings_inr(monthly_cost: float, usage_hours_30d: float) -> int:
    """Whole rupees shown in UI copy; sum of these equals dashboard totals."""
    return int(estimate_cancellation_savings_inr(monthly_cost, usage_hours_30d))


def yearly_from_monthly(monthly_inr: float) -> float:
    return round(max(0.0, float(monthly_inr or 0)) * 12.0, 2)


def _usage_hours_for_subscription(cur, user_id: int, subscription_id: int) -> float:
    cur.execute(
        """
        SELECT COALESCE(SUM(aus.usage_minutes), 0)::float
        FROM app_usage_signals aus
        INNER JOIN subscriptions s ON s.user_id = aus.user_id
          AND s.linked_app_package = aus.app_package
        WHERE s.user_id = %s AND s.id = %s
          AND aus.signal_date >= (CURRENT_DATE - INTERVAL '30 days');
        """,
        (user_id, subscription_id),
    )
    row = cur.fetchone()
    return usage_hours_from_minutes(float(row[0] or 0) if row else 0)


def sync_at_risk_waste_fields(conn: PgConnection, user_id: int) -> dict[str, Any]:
    """
    Recompute verdict_monthly_waste for every at-risk linked subscription so
    SUM(verdict_monthly_waste) == sum of per-card 'could save' amounts.
    """
    packages = fetch_linked_packages(conn, user_id)
    if not packages:
        return {"monthly_total_inr": 0.0, "yearly_total_inr": 0.0, "at_risk_count": 0, "lines": []}

    cur = conn.cursor()
    total = 0.0
    lines: list[dict[str, Any]] = []
    try:
        cur.execute(
            """
            SELECT id, merchant, COALESCE(monthly_cost, 0)::float,
                   COALESCE(current_verdict, '')
            FROM subscriptions
            WHERE user_id = %s
              AND linked_app_package = ANY(%s::varchar[])
              AND COALESCE(current_verdict, '') IN ('declining', 'dormant', 'dead');
            """,
            (user_id, packages),
        )
        for sid, merchant, cost, verdict in cur.fetchall():
            hours = _usage_hours_for_subscription(cur, user_id, int(sid))
            waste_display = display_savings_inr(float(cost), hours)
            total += float(waste_display)
            cur.execute(
                """
                UPDATE subscriptions SET verdict_monthly_waste = %s WHERE id = %s;
                """,
                (float(waste_display), int(sid)),
            )
            lines.append(
                {
                    "subscription_id": int(sid),
                    "merchant": merchant,
                    "verdict": verdict,
                    "monthly_cost_inr": round(float(cost), 2),
                    "usage_hours_30d": round(hours, 1),
                    "potential_savings_inr": waste_display,
                }
            )
    finally:
        cur.close()

    monthly = round(total, 2)
    return {
        "monthly_total_inr": monthly,
        "yearly_total_inr": yearly_from_monthly(monthly),
        "at_risk_count": len(lines),
        "lines": lines,
    }
