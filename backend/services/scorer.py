"""Health score calculator (0–100) with breakdown and recommendations."""

from __future__ import annotations

from datetime import date
from typing import Any

from models.schemas import HealthScoreResponse
from services.dashboard_scope import fetch_dashboard_mode, normalize_dashboard_mode
from services.financial_behavior import fetch_planning_snapshot, score_emi_points, score_planning_points
from services.ledger_summary import fetch_ledger_summary, persist_monthly_summary_row


def _month_key(y: int, m: int) -> int:
    return y * 12 + m


def _shift_month(y: int, m: int, delta: int) -> tuple[int, int]:
    idx = _month_key(y, m) + delta
    ny = (idx - 1) // 12
    nm = (idx - 1) % 12 + 1
    return ny, nm


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def health_band_for_score(score: int | None) -> tuple[str, str]:
    """
    Overall financial health band (not month-over-month trend).
    Shown in UI instead of misusing IMPROVING/DECLINING/STABLE trend labels.
    """
    if score is None:
        return "UNKNOWN", "—"
    s = int(score)
    if s >= 70:
        return "STABLE", "Stable"
    if s >= 60:
        return "MODERATE", "Moderate"
    if s >= 50:
        return "AT_RISK", "Needs attention"
    return "CRITICAL", "Critical"


def refresh_user_health_score(
    conn,
    user_id: int,
    month: int | None = None,
    year: int | None = None,
    scope: str | None = None,
    *,
    invalidate_insights: bool = True,
) -> HealthScoreResponse:
    """
    Recalculate health from live DB (transactions + EMI + planners) and persist.
    Call after EMI / purchase / festival / upload mutations.
    """
    today = date.today()
    m = month if month is not None else today.month
    y = year if year is not None else today.year
    hs = calculate_health_score(conn, user_id, m, y, scope=scope)
    if invalidate_insights and hs.score is not None:
        try:
            from services.openai_service import invalidate_insight_cache

            cur = conn.cursor()
            try:
                mode = (
                    normalize_dashboard_mode(scope)
                    if scope is not None
                    else fetch_dashboard_mode(cur, user_id)
                )
            finally:
                cur.close()
            invalidate_insight_cache(conn, user_id, m, y, mode)
        except Exception:
            pass
    return hs


def persist_health_score(conn, user_id: int, month: int, year: int, score: int) -> None:
    """Keep monthly_summary.health_score aligned with live calculator."""
    if score is None:
        return
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE monthly_summary
            SET health_score = %s
            WHERE user_id = %s AND month = %s AND year = %s;
            """,
            (int(score), user_id, month, year),
        )
        if cur.rowcount == 0:
            cur.execute(
                """
                INSERT INTO monthly_summary (user_id, month, year, health_score)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, month, year) DO UPDATE SET health_score = EXCLUDED.health_score;
                """,
                (user_id, month, year, int(score)),
            )
    except Exception:
        pass
    finally:
        cur.close()


def calculate_health_score(
    conn,
    user_id: int,
    month: int,
    year: int,
    scope: str | None = None,
) -> HealthScoreResponse:
    cur = conn.cursor()
    try:
        today = date.today()
        mode = (
            normalize_dashboard_mode(scope)
            if scope is not None
            else fetch_dashboard_mode(cur, user_id)
        )
        ledger = fetch_ledger_summary(cur, user_id, month, year, scope=mode)

        if not ledger.get("has_enough_data"):
            return HealthScoreResponse(
                score=None,
                grade="",
                components={},
                trend="STABLE",
                health_band="UNKNOWN",
                health_label="—",
                recommendations=[],
                savings_rate=None,
                reason="not_enough_data",
                message="Upload more statements to calculate your Health Score",
                days_needed=30,
                days_available=int(ledger.get("distinct_days_90d") or 0),
                mode=mode,
            )

        total_income = float(ledger.get("month_credits_inr") or 0)
        total_expense = float(ledger.get("month_debit_spend_inr") or 0)
        savings_rate = float(ledger.get("savings_rate_pct") or 0)
        anomaly_count = int(ledger.get("anomaly_count") or 0)
        ncat = int(ledger.get("distinct_categories") or 0)
        income_basis = float(ledger.get("income_basis_inr") or 0)
        planning = fetch_planning_snapshot(cur, user_id, income_basis=income_basis)

        if total_income <= 0:
            savings_points = 0
        elif savings_rate >= 30:
            savings_points = 22
        elif savings_rate >= 20:
            savings_points = 16
        elif savings_rate >= 10:
            savings_points = 11
        elif savings_rate >= 0:
            savings_points = 6
        else:
            savings_points = 0

        if anomaly_count == 0:
            anomaly_points = 13
        elif anomaly_count <= 2:
            anomaly_points = 9
        elif anomaly_count <= 4:
            anomaly_points = 5
        else:
            anomaly_points = 0

        if total_income > 0:
            ratio = total_expense / total_income
        else:
            ratio = 2.0
        if ratio <= 0.5:
            expense_points = 18
        elif ratio <= 0.7:
            expense_points = 13
        elif ratio <= 0.9:
            expense_points = 7
        elif ratio <= 1.0:
            expense_points = 3
        else:
            expense_points = 0

        prev_keys = [_shift_month(year, month, -i) for i in range(1, 4)]
        positive_months = 0
        for py, pm in prev_keys:
            cur.execute(
                """
                SELECT COALESCE(savings_rate, 0) FROM monthly_summary
                WHERE user_id = %s AND month = %s AND year = %s;
                """,
                (user_id, pm, py),
            )
            pr = cur.fetchone()
            if pr and float(pr[0] or 0) > 0:
                positive_months += 1
        if positive_months >= 3:
            consistency_points = 10
        elif positive_months == 2:
            consistency_points = 7
        elif positive_months == 1:
            consistency_points = 3
        else:
            consistency_points = 0

        if ncat >= 5:
            diversity_points = 5
        elif ncat == 4:
            diversity_points = 4
        elif ncat == 3:
            diversity_points = 2
        else:
            diversity_points = 0

        emi_points = score_emi_points(planning.get("emi_burden_pct"))
        planning_points = score_planning_points(planning, income_basis)

        score = int(
            min(
                100,
                savings_points
                + anomaly_points
                + expense_points
                + consistency_points
                + diversity_points
                + emi_points
                + planning_points,
            )
        )
        if total_income <= 0:
            score = min(score, 45)

        py, pm = _shift_month(year, month, -1)
        cur.execute(
            """
            SELECT COALESCE(health_score, 0) FROM monthly_summary
            WHERE user_id = %s AND month = %s AND year = %s;
            """,
            (user_id, pm, py),
        )
        prev_row = cur.fetchone()
        prev_score = int(prev_row[0]) if prev_row else score
        diff = score - prev_score
        if diff >= 5:
            trend = "IMPROVING"
        elif diff <= -5:
            trend = "DECLINING"
        else:
            trend = "STABLE"

        components: dict[str, Any] = {
            "ledger_scope": mode,
            "month_credits_inr": ledger.get("month_credits_inr"),
            "month_debit_spend_inr": ledger.get("month_debit_spend_inr"),
            "month_net_inr": ledger.get("month_net_inr"),
            "ytd_saved_inr": ledger.get("ytd_saved_inr"),
            "savings_rate_pct": savings_rate,
            "savings_points": savings_points,
            "anomaly_count": anomaly_count,
            "anomaly_points": anomaly_points,
            "expense_to_income_ratio": round(ratio, 3) if total_income > 0 else None,
            "expense_points": expense_points,
            "consistency_positive_months_of_3": positive_months,
            "consistency_points": consistency_points,
            "distinct_categories": ncat,
            "diversity_points": diversity_points,
            "emi_monthly_total": planning.get("emi_monthly_total"),
            "emi_burden_pct": planning.get("emi_burden_pct"),
            "emi_points": emi_points,
            "purchase_monthly_reserve": planning.get("purchase_monthly_reserve"),
            "festival_monthly_reserve": planning.get("festival_monthly_reserve"),
            "events_monthly_reserve": planning.get("events_monthly_reserve"),
            "planning_burden_pct": planning.get("planning_burden_pct"),
            "upcoming_important_days": planning.get("upcoming_important_days"),
            "active_purchase_goals": planning.get("active_purchase_goals"),
            "active_festivals": planning.get("active_festivals"),
            "purchase_goals_on_track": planning.get("purchase_goals_on_track"),
            "purchase_goal_progress_pct": planning.get("purchase_goal_progress_pct"),
            "festival_progress_pct": planning.get("festival_progress_pct"),
            "planning_points": planning_points,
        }

        weakest = min(
            [
                ("savings rate", savings_points, 22),
                ("transaction security", anomaly_points, 13),
                ("expense control", expense_points, 18),
                ("savings consistency", consistency_points, 10),
                ("category balance", diversity_points, 5),
                ("EMI burden", emi_points, 17),
                ("goals & events", planning_points, 15),
            ],
            key=lambda x: x[1] / max(x[2], 1),
        )
        recs: list[str] = []
        label = weakest[0]
        if label == "savings rate":
            recs.append("Auto-transfer 10% of salary to savings on pay day.")
        elif label == "transaction security":
            recs.append("Review flagged transactions in FraudShield.")
        elif label == "expense control":
            recs.append("Cap monthly debits below 70% of income.")
        elif label == "savings consistency":
            recs.append("Aim for positive savings three months in a row.")
        elif label == "EMI burden":
            recs.append("EMIs are heavy vs income — check EMI Tracker before new loans.")
        elif label == "goals & events":
            recs.append("Sync Purchase Planner and Festival budgets with monthly targets.")
        else:
            recs.append("Spread spend across categories to avoid concentration risk.")
        recs.append("Check weekly UPI totals so month-end surprises stay small.")

        persist_health_score(conn, user_id, month, year, score)
        persist_monthly_summary_row(
            conn,
            user_id,
            month,
            year,
            ledger,
            health_score=score,
            anomaly_count=anomaly_count,
        )

        band_id, band_label = health_band_for_score(score)
        return HealthScoreResponse(
            score=score,
            grade=_grade(score),
            components=components,
            trend=trend,
            health_band=band_id,
            health_label=band_label,
            recommendations=recs[:4],
            savings_rate=savings_rate,
            mode=mode,
        )
    finally:
        cur.close()
