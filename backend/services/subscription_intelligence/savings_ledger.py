"""Subscription savings rollups — realized cancellations + live at-risk waste (linked apps only)."""
from __future__ import annotations

from datetime import date
from typing import Any

from psycopg2.extensions import connection as PgConnection

from services.subscription_intelligence.linked_apps import fetch_linked_packages
from services.subscription_intelligence.savings_math import (
    sync_at_risk_waste_fields,
    yearly_from_monthly,
)


def sync_current_month_waste_snapshot(conn: PgConnection, user_id: int, monthly_waste: float) -> None:
    """Upsert this month's waste_prevented_* (monthly and yearly stay in sync)."""
    bucket = date.today().replace(day=1)
    waste_m = round(max(0.0, float(monthly_waste or 0)), 2)
    waste_y = yearly_from_monthly(waste_m)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO user_subscription_savings (
              user_id, month, subscriptions_cancelled, amount_saved,
              waste_prevented_monthly, waste_prevented_yearly, updated_at
            )
            VALUES (%s, %s, 0, 0, %s, %s, NOW())
            ON CONFLICT (user_id, month) DO UPDATE SET
              waste_prevented_monthly = EXCLUDED.waste_prevented_monthly,
              waste_prevented_yearly = EXCLUDED.waste_prevented_yearly,
              updated_at = NOW();
            """,
            (user_id, bucket, waste_m, waste_y),
        )
    finally:
        cur.close()


def build_savings_payload(conn: PgConnection, user_id: int) -> dict[str, Any]:
    """Return savings dashboard numbers aligned with Possible savings card."""
    packages = fetch_linked_packages(conn, user_id)
    rollup = sync_at_risk_waste_fields(conn, user_id)
    waste_m = float(rollup["monthly_total_inr"])
    waste_y = float(rollup["yearly_total_inr"])
    at_risk_n = int(rollup["at_risk_count"])

    if packages:
        sync_current_month_waste_snapshot(conn, user_id, waste_m)

    cur = conn.cursor()
    try:
        if packages:
            cur.execute(
                """
                SELECT COALESCE(subscriptions_cancelled, 0), COALESCE(amount_saved, 0)
                FROM user_subscription_savings
                WHERE user_id = %s AND month = date_trunc('month', CURRENT_DATE)::date;
                """,
                (user_id,),
            )
            this_month = cur.fetchone() or (0, 0)
            cur.execute(
                """
                SELECT COALESCE(SUM(subscriptions_cancelled), 0), COALESCE(SUM(amount_saved), 0)
                FROM user_subscription_savings
                WHERE user_id = %s AND month >= date_trunc('year', CURRENT_DATE)::date;
                """,
                (user_id,),
            )
            ytd = cur.fetchone() or (0, 0)
            cur.execute(
                """
                SELECT COALESCE(SUM(subscriptions_cancelled), 0), COALESCE(SUM(amount_saved), 0)
                FROM user_subscription_savings
                WHERE user_id = %s;
                """,
                (user_id,),
            )
            all_time = cur.fetchone() or (0, 0)
        else:
            this_month = (0, 0)
            ytd = (0, 0)
            all_time = (0, 0)
    except Exception:
        this_month = (0, 0)
        ytd = (0, 0)
        all_time = (0, 0)
    finally:
        cur.close()

    realized_m = round(float(this_month[1] or 0), 2)
    realized_ytd = round(float(ytd[1] or 0), 2)
    cancelled_m = int(this_month[0] or 0)
    cancelled_ytd = int(ytd[0] or 0)

    return {
        "success": True,
        "at_risk_subscriptions": at_risk_n,
        "savings_breakdown": rollup.get("lines") or [],
        "this_month": {
            "subscriptions_cancelled": cancelled_m,
            "amount_saved_inr": realized_m,
            "waste_prevented_monthly_inr": waste_m,
            "waste_prevented_yearly_inr": waste_y,
            "total_impact_monthly_inr": round(realized_m + waste_m, 2),
        },
        "this_year": {
            "subscriptions_cancelled": cancelled_ytd,
            "amount_saved_inr": realized_ytd,
            "waste_prevented_monthly_inr": waste_m,
            "waste_prevented_yearly_inr": waste_y,
            "total_impact_yearly_inr": round(realized_ytd + waste_y, 2),
        },
        "all_time": {
            "subscriptions_cancelled": int(all_time[0] or 0),
            "amount_saved_inr": round(float(all_time[1] or 0), 2),
        },
    }
