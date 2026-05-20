"""Paired substitution insights from real usage + substitution graph."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_backend_dir = Path(__file__).resolve().parents[2]
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from psycopg2.extensions import connection as PgConnection

from services.subscription_intelligence.linked_apps import fetch_linked_packages
from services.subscription_intelligence.verdict_engine import compute_pkg_growth


def detect_substitutions(conn: PgConnection, user_id: int) -> list[dict[str, Any]]:
    cur = conn.cursor()
    pkgs = fetch_linked_packages(conn, user_id)
    if not pkgs:
        return []
    try:
        today = date.today()
        last30_start = today - timedelta(days=30)
        prev30_start = today - timedelta(days=60)
        prev30_end = today - timedelta(days=30)

        cur.execute(
            """
            SELECT id, merchant, monthly_cost, intelligence_category, linked_app_package, current_verdict
            FROM subscriptions
            WHERE user_id = %s AND linked_app_package = ANY(%s::varchar[])
              AND current_verdict IN ('declining', 'dormant', 'dead');
            """,
            (user_id, pkgs),
        )
        subs = cur.fetchall()
        out: list[dict[str, Any]] = []

        cur.execute("SELECT category, primary_app, substitute_apps, category_display_name FROM subscription_substitutions;")
        graph = cur.fetchall()

        for sub_id, merchant, monthly_cost, cat, primary_pkg, verdict in subs:
            for g_cat, g_primary, subs_json, display in graph:
                if g_primary != primary_pkg:
                    continue
                apps = subs_json
                if isinstance(apps, str):
                    apps = json.loads(apps)
                if not apps:
                    continue
                cur.execute(
                    """
                    SELECT COALESCE(SUM(usage_minutes), 0)::bigint
                    FROM app_usage_signals
                    WHERE user_id = %s AND app_package = %s AND signal_date >= %s;
                    """,
                    (user_id, primary_pkg, last30_start),
                )
                primary_last = int(cur.fetchone()[0] or 0)
                cur.execute(
                    """
                    SELECT COALESCE(SUM(usage_minutes), 0)::bigint
                    FROM app_usage_signals
                    WHERE user_id = %s AND app_package = %s AND signal_date >= %s AND signal_date < %s;
                    """,
                    (user_id, primary_pkg, prev30_start, prev30_end),
                )
                primary_prev = int(cur.fetchone()[0] or 0)
                p_delta = (primary_last - primary_prev) / max(float(primary_prev), 1.0)

                best_pkg = None
                best_growth = 0.0
                for alt in apps:
                    g = compute_pkg_growth(cur, user_id, alt, last30_start, today, prev30_start, prev30_end)
                    if g > best_growth:
                        best_growth = g
                        best_pkg = alt

                if p_delta < -0.35 and best_growth >= 1.8 and best_pkg:
                    cur.execute(
                        """
                        SELECT COALESCE(SUM(usage_minutes), 0)::bigint
                        FROM app_usage_signals
                        WHERE user_id = %s AND app_package = %s AND signal_date >= %s;
                        """,
                        (user_id, best_pkg, last30_start),
                    )
                    alt_min = int(cur.fetchone()[0] or 0)
                    out.append(
                        {
                            "subscription_id": sub_id,
                            "from_merchant": merchant,
                            "from_package": primary_pkg,
                            "to_package": best_pkg,
                            "category_display": display,
                            "monthly_cost": float(monthly_cost or 0),
                            "headline": f"You migrated usage from {merchant.split()[0]} toward a substitute in {display}.",
                            "body": (
                                f"Primary app usage trend is down sharply while {best_pkg.split('.')[-1]} is up ~{best_growth:.1f}× vs prior 30 days. "
                                f"Consider cancelling {merchant} (≈₹{float(monthly_cost or 0):,.0f}/mo) if the new habit stuck."
                            ),
                            "from_last30_minutes": primary_last,
                            "to_last30_minutes": alt_min,
                        }
                    )
                break
        return out
    finally:
        cur.close()


def detect_category_migrations(conn: PgConnection, user_id: int) -> list[dict[str, Any]]:
    """
    Same intelligence_category: one subscription sharply down, another materially up
    (usage migration signal). Complements graph-based detect_substitutions().
    """
    cur = conn.cursor()
    pkgs = fetch_linked_packages(conn, user_id)
    if not pkgs:
        return []
    insights: list[dict[str, Any]] = []
    try:
        cur.execute(
            """
            SELECT
                s.id,
                s.merchant,
                COALESCE(s.monthly_cost, 0)::float,
                s.intelligence_category,
                calc.current_usage_hours,
                calc.previous_usage_hours,
                calc.change_percentage
            FROM subscriptions s
            CROSS JOIN LATERAL calculate_usage_change(s.user_id, s.id, 30, 30) AS calc
            WHERE s.user_id = %s
              AND s.linked_app_package = ANY(%s::varchar[])
              AND s.intelligence_category IS NOT NULL
              AND length(trim(s.intelligence_category)) > 0
              AND COALESCE(calc.change_percentage, 0) < -50;
            """,
            (user_id, pkgs),
        )
        declining = cur.fetchall()
        for dec_id, dec_name, dec_cost, category, _dc, _dp, _dchg in declining:
            cur.execute(
                """
                SELECT
                    s.id,
                    s.merchant,
                    COALESCE(s.monthly_cost, 0)::float,
                    calc.current_usage_hours,
                    calc.change_percentage
                FROM subscriptions s
                CROSS JOIN LATERAL calculate_usage_change(s.user_id, s.id, 30, 30) AS calc
                WHERE s.user_id = %s
                  AND s.id <> %s
                  AND s.intelligence_category IS NOT DISTINCT FROM %s
                  AND s.linked_app_package = ANY(%s::varchar[])
                  AND COALESCE(calc.current_usage_hours, 0) > 10
                  AND COALESCE(calc.change_percentage, 0) > 0;
                """,
                (user_id, int(dec_id), category, pkgs),
            )
            for thr_id, thr_name, thr_cost, thr_cur, thr_chg in cur.fetchall():
                dec_cost_f = float(dec_cost or 0)
                insights.append(
                    {
                        "insight_type": "migration_detected",
                        "primary_subscription_id": int(dec_id),
                        "secondary_subscription_id": int(thr_id),
                        "title": "You switched apps",
                        "description": (
                            f"Your time moved from {dec_name} to {thr_name} "
                            f"(same type of app: {category})."
                        ),
                        "recommendation": (
                            f"If you prefer {thr_name} now, cancelling {dec_name} "
                            f"could save about ₹{int(round(dec_cost_f))} per month."
                        ),
                        "potential_savings_monthly": dec_cost_f,
                        "potential_savings_yearly": round(dec_cost_f * 12, 2),
                        "confidence_score": 0.85,
                    }
                )
        return insights
    except Exception:
        return []
    finally:
        cur.close()


def save_category_migration_insights(conn: PgConnection, user_id: int, insights: list[dict[str, Any]]) -> int:
    """Persist category migration cards into subscription_intelligence_insights."""
    if not insights:
        return 0
    cur = conn.cursor()
    n = 0
    try:
        for ins in insights:
            pid = ins.get("primary_subscription_id")
            sid2 = ins.get("secondary_subscription_id")
            if pid is None or sid2 is None:
                continue
            dedupe_key = f"migration_cat:{pid}:{sid2}"[:220]
            title = str(ins.get("title") or "Migration detected")[:240]
            desc = str(ins.get("description") or "")
            rec = str(ins.get("recommendation") or "")
            body = f"{desc}\n\n{rec}".strip()
            cur.execute(
                """
                INSERT INTO subscription_intelligence_insights (
                    user_id, subscription_id, dedupe_key, insight_type, title, body, priority, updated_at
                ) VALUES (%s, %s, %s, 'migration_detected', %s, %s, 1, NOW())
                ON CONFLICT (user_id, dedupe_key) DO UPDATE SET
                    title = EXCLUDED.title,
                    body = EXCLUDED.body,
                    subscription_id = COALESCE(EXCLUDED.subscription_id, subscription_intelligence_insights.subscription_id),
                    priority = LEAST(subscription_intelligence_insights.priority, EXCLUDED.priority),
                    updated_at = NOW();
                """,
                (user_id, int(pid), dedupe_key, title, body),
            )
            n += 1
        return n
    finally:
        cur.close()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    _root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_root))
    from db import get_connection

    uid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print("=" * 60)
    print("TESTING SUBSTITUTION DETECTOR (category migrations)")
    print("=" * 60)
    with get_connection() as conn:
        migrations = detect_category_migrations(conn, uid)
        print(f"\nmigrations: {len(migrations)}")
        for m in migrations[:10]:
            print(f"  - {m.get('title')}: {m.get('description', '')[:70]}")
        if migrations:
            n = save_category_migration_insights(conn, uid, migrations)
            conn.commit()
            print(f"\nsaved_rows: {n}")
    print("=" * 60)
