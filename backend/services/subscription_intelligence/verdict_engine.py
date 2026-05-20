"""
Deterministic subscription verdict engine (NOT an LLM).
Reads real app_usage_signals rows from PostgreSQL.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from psycopg2.extensions import connection as PgConnection

from services.subscription_intelligence.linked_apps import fetch_linked_packages
from services.subscription_intelligence.savings_math import (
    display_savings_inr,
    estimate_cancellation_savings_inr,
    usage_hours_from_minutes,
)


@dataclass
class VerdictResult:
    verdict: str
    confidence: int
    reason: str
    monthly_waste: float
    usage_delta_30d: float = 0.0
    substitution: dict[str, Any] | None = None


def _sum_minutes(rows: list[tuple]) -> int:
    return int(sum(int(r[0] or 0) for r in rows))


def _sum_sessions(rows: list[tuple]) -> int:
    return int(sum(int(r[1] or 0) for r in rows))


def get_substitutes(cur, category: str, primary_pkg: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT substitute_apps, category_display_name
        FROM subscription_substitutions
        WHERE category = %s AND primary_app = %s
        LIMIT 1;
        """,
        (category, primary_pkg),
    )
    row = cur.fetchone()
    if not row:
        return []
    apps, display = row[0], row[1]
    if isinstance(apps, str):
        apps = json.loads(apps)
    return [{"package": p, "display_name": display} for p in (apps or [])]


def compute_pkg_growth(cur, user_id: int, pkg: str, last_start: date, last_end: date, prev_start: date, prev_end: date) -> float:
    cur.execute(
        """
        SELECT COALESCE(SUM(usage_minutes), 0)::bigint
        FROM app_usage_signals
        WHERE user_id = %s AND app_package = %s AND signal_date >= %s AND signal_date < %s;
        """,
        (user_id, pkg, last_start, last_end),
    )
    last_m = int(cur.fetchone()[0] or 0)
    cur.execute(
        """
        SELECT COALESCE(SUM(usage_minutes), 0)::bigint
        FROM app_usage_signals
        WHERE user_id = %s AND app_package = %s AND signal_date >= %s AND signal_date < %s;
        """,
        (user_id, pkg, prev_start, prev_end),
    )
    prev_m = int(cur.fetchone()[0] or 0)
    return float(last_m) / max(float(prev_m), 1.0)


def compute_pro_threshold(category: str) -> float:
    """Hours per month above which we consider 'heavy' usage for upgrade hints."""
    return {"music": 40, "video": 35, "professional": 25, "productivity": 30, "fitness": 10, "news": 15}.get(category, 25)


def has_pro_tier(name: str) -> bool:
    n = (name or "").lower()
    return any(
        k in n
        for k in (
            "chatgpt",
            "notion",
            "canva",
            "youtube",
            "linkedin",
            "spotify",
            "netflix",
            "prime",
        )
    )


def evaluate_subscription(conn: PgConnection, subscription_id: int) -> VerdictResult | None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, user_id, merchant, monthly_cost, intelligence_category, linked_app_package, is_pro
            FROM subscriptions WHERE id = %s;
            """,
            (subscription_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        _id, user_id, merchant, monthly_cost, category, linked_pkg, is_pro = row
        monthly_cost = float(monthly_cost or 0)
        category = (category or "other").lower()
        merchant = merchant or ""

        if not linked_pkg:
            return VerdictResult(
                verdict="declining",
                confidence=40,
                reason="Link your phone usage in Device Intelligence to get personalised advice.",
                monthly_waste=estimate_cancellation_savings_inr(monthly_cost, 0.0),
                usage_delta_30d=0.0,
                substitution=None,
            )

        today = date.today()
        last30_start = today - timedelta(days=30)
        prev30_start = today - timedelta(days=60)
        prev30_end = today - timedelta(days=30)
        d60 = today - timedelta(days=60)

        cur.execute(
            """
            SELECT usage_minutes, session_count
            FROM app_usage_signals
            WHERE user_id = %s AND app_package = %s AND signal_date >= %s;
            """,
            (user_id, linked_pkg, last30_start),
        )
        last30_rows = cur.fetchall()
        cur.execute(
            """
            SELECT usage_minutes, session_count
            FROM app_usage_signals
            WHERE user_id = %s AND app_package = %s AND signal_date >= %s AND signal_date < %s;
            """,
            (user_id, linked_pkg, prev30_start, prev30_end),
        )
        prev30_rows = cur.fetchall()

        last30_minutes = _sum_minutes(last30_rows)
        prev30_minutes = _sum_minutes(prev30_rows)
        delta = (last30_minutes - prev30_minutes) / max(float(prev30_minutes), 1.0)

        cur.execute(
            """
            SELECT usage_minutes, session_count
            FROM app_usage_signals
            WHERE user_id = %s AND app_package = %s AND signal_date >= %s;
            """,
            (user_id, linked_pkg, d60),
        )
        last60_rows = cur.fetchall()
        last60_minutes = _sum_minutes(last60_rows)
        last30_sessions = _sum_sessions(last30_rows)
        prev30_sessions = _sum_sessions(prev30_rows)

        # DEAD: near-zero 60d
        hours_30 = usage_hours_from_minutes(last30_minutes)
        if last30_minutes < 5 and prev30_minutes < 5:
            waste = float(display_savings_inr(monthly_cost, hours_30))
            return VerdictResult(
                verdict="dead",
                confidence=95,
                reason="Almost no usage in the last 60 days — you may be paying for nothing.",
                monthly_waste=waste,
                usage_delta_30d=delta,
                substitution=None,
            )

        substitutes = get_substitutes(cur, category, linked_pkg)
        top_sub: dict[str, Any] | None = None
        max_growth = 0.0
        for s in substitutes:
            g = compute_pkg_growth(cur, user_id, s["package"], last30_start, today, prev30_start, prev30_end)
            if g > max_growth:
                max_growth = g
                top_sub = s

        if delta < -0.4 and max_growth >= 2.0 and top_sub:
            alt = top_sub.get("display_name", "another app")
            waste = float(display_savings_inr(monthly_cost, hours_30))
            return VerdictResult(
                verdict="dead",
                confidence=92,
                reason=f"You seem to be using {alt} more instead.",
                monthly_waste=waste,
                usage_delta_30d=delta,
                substitution={"package": top_sub["package"], "label": top_sub.get("display_name", "")},
            )

        if last30_sessions < 2 and prev30_sessions < 4:
            waste = float(display_savings_inr(monthly_cost, hours_30))
            return VerdictResult(
                verdict="dormant",
                confidence=80,
                reason="You opened this fewer than 2 times in the last 30 days.",
                monthly_waste=waste,
                usage_delta_30d=delta,
                substitution=None,
            )

        if delta < -0.4:
            pct = abs(delta * 100)
            waste_display = display_savings_inr(monthly_cost, hours_30)
            return VerdictResult(
                verdict="declining",
                confidence=75,
                reason=(
                    f"You used this {pct:.0f}% less than the previous month. "
                    f"You could save about ₹{waste_display} per month if you cancel."
                ),
                monthly_waste=float(waste_display),
                usage_delta_30d=delta,
                substitution=None,
            )

        hours = hours_30
        if hours > compute_pro_threshold(category) and has_pro_tier(merchant) and not (is_pro or False):
            return VerdictResult(
                verdict="upgrade",
                confidence=85,
                reason=f"You spend about {hours:.0f} hours a month here — a paid plan may be worth it.",
                monthly_waste=0.0,
                usage_delta_30d=delta,
                substitution=None,
            )

        return VerdictResult(
            verdict="thriving",
            confidence=90,
            reason="You use this regularly — about the same or more than last month.",
            monthly_waste=0.0,
            usage_delta_30d=delta,
            substitution=None,
        )
    finally:
        cur.close()


def persist_verdict(conn: PgConnection, subscription_id: int, vr: VerdictResult) -> None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE subscriptions SET
              current_verdict = %s,
              verdict_confidence = %s,
              verdict_reason = %s,
              verdict_monthly_waste = %s,
              last_evaluated_at = NOW()
            WHERE id = %s;
            """,
            (vr.verdict, vr.confidence, vr.reason, vr.monthly_waste, subscription_id),
        )
        cur.execute(
            """
            INSERT INTO verdict_history (subscription_id, verdict, usage_delta_30d, confidence, reason)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (subscription_id, vr.verdict, vr.usage_delta_30d, vr.confidence, vr.reason),
        )
    finally:
        cur.close()


def _linked_pkg_clause(conn: PgConnection, user_id: int) -> tuple[str, list[str]]:
    pkgs = fetch_linked_packages(conn, user_id)
    if not pkgs:
        return " AND FALSE ", []
    return " AND s.linked_app_package = ANY(%s::varchar[]) ", pkgs


def detect_thriving_subscriptions(conn: PgConnection, user_id: int) -> list[dict[str, Any]]:
    """
    Subscriptions with strong recent usage (>20h / 30d) and non-negative trend vs prior 30d.
    Uses DB function calculate_usage_change (migration 023).
    """
    cur = conn.cursor()
    extra, pkgs = _linked_pkg_clause(conn, user_id)
    params: list[Any] = [user_id]
    if pkgs:
        params.append(pkgs)
    try:
        cur.execute(
            f"""
            SELECT
                s.id,
                s.merchant,
                COALESCE(s.monthly_cost, 0)::float,
                calc.current_usage_hours,
                calc.previous_usage_hours,
                calc.change_percentage
            FROM subscriptions s
            CROSS JOIN LATERAL calculate_usage_change(s.user_id, s.id, 30, 30) AS calc
            WHERE s.user_id = %s
              AND s.linked_app_package IS NOT NULL
              AND length(trim(s.linked_app_package)) > 0
              AND COALESCE(calc.current_usage_hours, 0) > 20
              AND COALESCE(calc.change_percentage, 0) >= 0
              AND COALESCE(s.monthly_cost, 0) > 0
              {extra};
            """,
            tuple(params),
        )
        out: list[dict[str, Any]] = []
        for sid, merchant, cost, cur_h, prev_h, chg in cur.fetchall():
            chg_f = float(chg or 0)
            out.append(
                {
                    "subscription_id": int(sid),
                    "subscription_name": merchant or "",
                    "verdict": "thriving",
                    "reasoning": "You use this regularly — about the same or more than last month.",
                    "confidence_score": 0.90,
                    "current_usage_hours": float(cur_h or 0),
                    "previous_usage_hours": float(prev_h or 0),
                    "usage_change_percentage": chg_f,
                    "monthly_cost": float(cost or 0),
                }
            )
        return out
    except Exception:
        return []
    finally:
        cur.close()


def detect_declining_subscriptions(conn: PgConnection, user_id: int) -> list[dict[str, Any]]:
    """Usage down more than 50% (percentage points) vs prior 30 days."""
    cur = conn.cursor()
    extra, pkgs = _linked_pkg_clause(conn, user_id)
    params: list[Any] = [user_id]
    if pkgs:
        params.append(pkgs)
    try:
        cur.execute(
            f"""
            SELECT
                s.id,
                s.merchant,
                COALESCE(s.monthly_cost, 0)::float,
                calc.current_usage_hours,
                calc.previous_usage_hours,
                calc.change_percentage
            FROM subscriptions s
            CROSS JOIN LATERAL calculate_usage_change(s.user_id, s.id, 30, 30) AS calc
            WHERE s.user_id = %s
              AND s.linked_app_package IS NOT NULL
              AND length(trim(s.linked_app_package)) > 0
              AND COALESCE(calc.change_percentage, 0) < -50
              {extra};
            """,
            tuple(params),
        )
        out: list[dict[str, Any]] = []
        for sid, merchant, cost, cur_h, prev_h, chg in cur.fetchall():
            cur_f = float(cur_h or 0)
            cost_f = float(cost or 0)
            chg_f = float(chg or 0)
            waste_display = display_savings_inr(cost_f, cur_f)
            out.append(
                {
                    "subscription_id": int(sid),
                    "subscription_name": merchant or "",
                    "verdict": "declining",
                    "reasoning": (
                        f"You used this {abs(int(round(chg_f)))}% less last month. "
                        f"You could save about ₹{waste_display} per month if you cancel."
                    ),
                    "confidence_score": 0.85,
                    "current_usage_hours": cur_f,
                    "previous_usage_hours": float(prev_h or 0),
                    "usage_change_percentage": chg_f,
                    "monthly_cost": cost_f,
                    "potential_monthly_savings": float(waste_display),
                    "potential_yearly_savings": float(waste_display) * 12,
                }
            )
        return out
    except Exception:
        return []
    finally:
        cur.close()


def detect_upgrade_opportunities_for_user(conn: PgConnection, user_id: int) -> list[dict[str, Any]]:
    """High in-app time on a low/zero nominal plan - suggest paid tier when not already is_pro."""
    cur = conn.cursor()
    extra, pkgs = _linked_pkg_clause(conn, user_id)
    params: list[Any] = [user_id]
    if pkgs:
        params.append(pkgs)
    try:
        cur.execute(
            f"""
            SELECT
                s.id,
                s.merchant,
                COALESCE(s.monthly_cost, 0)::float,
                calc.current_usage_hours,
                calc.previous_usage_hours,
                COALESCE(s.is_pro, FALSE)
            FROM subscriptions s
            CROSS JOIN LATERAL calculate_usage_change(s.user_id, s.id, 30, 30) AS calc
            WHERE s.user_id = %s
              AND s.linked_app_package IS NOT NULL
              AND length(trim(s.linked_app_package)) > 0
              AND COALESCE(s.is_pro, FALSE) IS NOT TRUE
              AND COALESCE(calc.current_usage_hours, 0) > 15
              AND (
                    COALESCE(s.monthly_cost, 0) <= 0
                    OR lower(coalesce(s.merchant, '')) LIKE '%%free%%'
                    OR lower(coalesce(s.merchant, '')) LIKE '%%basic%%'
                )
              {extra};
            """,
            tuple(params),
        )
        out: list[dict[str, Any]] = []
        for sid, merchant, cost, cur_h, prev_h, _is_pro in cur.fetchall():
            m = merchant or ""
            if not has_pro_tier(m):
                continue
            cur_f = float(cur_h or 0)
            out.append(
                {
                    "subscription_id": int(sid),
                    "subscription_name": m,
                    "verdict": "upgrade_recommended",
                    "reasoning": f"You spend about {int(cur_f)} hours a month here — a paid plan may be worth it.",
                    "confidence_score": 0.80,
                    "current_usage_hours": cur_f,
                    "previous_usage_hours": float(prev_h or 0),
                    "monthly_cost": float(cost or 0),
                }
            )
        return out
    except Exception:
        return []
    finally:
        cur.close()


def detect_dormant_subscriptions(conn: PgConnection, user_id: int) -> list[dict[str, Any]]:
    """Delegates to evaluate_subscription for verdict == dormant (session-aware)."""
    cur = conn.cursor()
    pkgs = fetch_linked_packages(conn, user_id)
    out: list[dict[str, Any]] = []
    try:
        if not pkgs:
            return []
        cur.execute(
            """
            SELECT id, merchant, COALESCE(monthly_cost, 0)::float
            FROM subscriptions
            WHERE user_id = %s AND linked_app_package = ANY(%s::varchar[])
            ORDER BY id;
            """,
            (user_id, pkgs),
        )
        for sid, merchant, mc in cur.fetchall():
            vr = evaluate_subscription(conn, int(sid))
            if vr is None or vr.verdict != "dormant":
                continue
            waste_display = int(float(vr.monthly_waste or 0))
            out.append(
                {
                    "subscription_id": int(sid),
                    "subscription_name": merchant or "",
                    "verdict": "dormant",
                    "reasoning": vr.reason,
                    "confidence_score": round((vr.confidence or 0) / 100.0, 2),
                    "monthly_cost": float(mc or 0),
                    "potential_monthly_savings": float(waste_display),
                    "potential_yearly_savings": float(waste_display) * 12,
                }
            )
        return out
    except Exception:
        return []
    finally:
        cur.close()


def refresh_all_subscription_verdicts(conn: PgConnection, user_id: int) -> int:
    """Re-run evaluate_subscription for device-linked apps only."""
    pkgs = fetch_linked_packages(conn, user_id)
    cur = conn.cursor()
    try:
        if not pkgs:
            return 0
        cur.execute(
            """
            SELECT id FROM subscriptions
            WHERE user_id = %s AND linked_app_package = ANY(%s::varchar[])
            ORDER BY id;
            """,
            (user_id, pkgs),
        )
        sids = [int(r[0]) for r in cur.fetchall()]
    finally:
        cur.close()
    updated = 0
    for sid in sids:
        vr = evaluate_subscription(conn, sid)
        if vr is not None:
            persist_verdict(conn, sid, vr)
            updated += 1
    return updated


def generate_all_verdict_reports(conn: PgConnection, user_id: int) -> dict[str, list[dict[str, Any]]]:
    """Run batch detectors (SQL + evaluate_subscription) for dashboards and QA."""
    return {
        "thriving": detect_thriving_subscriptions(conn, user_id),
        "declining": detect_declining_subscriptions(conn, user_id),
        "dormant": detect_dormant_subscriptions(conn, user_id),
        "upgrade_recommended": detect_upgrade_opportunities_for_user(conn, user_id),
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path

    _root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_root))
    from db import get_connection

    uid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print("=" * 60)
    print("TESTING VERDICT ENGINE (batch SQL + evaluate_subscription)")
    print("=" * 60)
    with get_connection() as conn:
        verdicts = generate_all_verdict_reports(conn, uid)
        for bucket in ("thriving", "declining", "dormant", "upgrade_recommended"):
            rows = verdicts.get(bucket) or []
            print(f"\n{bucket}: {len(rows)}")
            for v in rows[:8]:
                name = v.get("subscription_name") or "?"
                print(f"  - {name}: {v.get('reasoning', '')[:72]}")
    print("\n" + "=" * 60)
    print("VERDICT ENGINE TEST COMPLETE")
    print("=" * 60)
