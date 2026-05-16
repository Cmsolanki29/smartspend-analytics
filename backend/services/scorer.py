"""Health score calculator (0–100) with breakdown and recommendations."""

from __future__ import annotations

from datetime import date
from typing import Any

from models.schemas import HealthScoreResponse
from services.dashboard_scope import fetch_dashboard_mode, transaction_scope_sql


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


def calculate_health_score(conn, user_id: int, month: int, year: int) -> HealthScoreResponse:
    cur = conn.cursor()
    try:
        mode = fetch_dashboard_mode(cur, user_id)
        scope = transaction_scope_sql("t", mode)

        cur.execute(
            """
            SELECT total_income, total_expense, savings_rate, anomaly_count, COALESCE(health_score, 0)
            FROM monthly_summary
            WHERE user_id = %s AND month = %s AND year = %s;
            """,
            (user_id, month, year),
        )
        row = cur.fetchone()
        # Always compute component breakdown for the gauge UI (stored monthly_summary alone
        # used to return the wrong component shape — all bars showed 0/30).
        if not row:
            cur.execute(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN t.type = 'CREDIT' THEN t.amount ELSE 0 END), 0)::float,
                    COALESCE(SUM(CASE WHEN t.type = 'DEBIT' THEN t.amount ELSE 0 END), 0)::float
                FROM transactions t
                WHERE t.user_id = %s
                  AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
                  AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
                  AND ({scope});
                """,
                (user_id, month, year),
            )
            inc, exp = cur.fetchone()
            total_income = float(inc or 0)
            total_expense = float(exp or 0)
            savings_rate = (
                round((total_income - total_expense) / total_income * 100, 2) if total_income > 0 else 0.0
            )
            cur.execute(
                f"""
                SELECT COUNT(*) FROM transactions t
                WHERE t.user_id = %s AND t.anomaly_flag = TRUE
                  AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
                  AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
                  AND ({scope});
                """,
                (user_id, month, year),
            )
            anomaly_count = int(cur.fetchone()[0])
        else:
            total_income = float(row[0] or 0)
            total_expense = float(row[1] or 0)
            savings_rate = float(row[2] or 0)
            anomaly_count = int(row[3] or 0)

        if total_income <= 0:
            savings_points = 0
        elif savings_rate >= 30:
            savings_points = 30
        elif savings_rate >= 20:
            savings_points = 22
        elif savings_rate >= 10:
            savings_points = 15
        elif savings_rate >= 0:
            savings_points = 8
        else:
            savings_points = 0

        if anomaly_count == 0:
            anomaly_points = 20
        elif anomaly_count <= 2:
            anomaly_points = 14
        elif anomaly_count <= 4:
            anomaly_points = 8
        else:
            anomaly_points = 0

        if total_income > 0:
            ratio = total_expense / total_income
        else:
            ratio = 2.0
        if ratio <= 0.5:
            expense_points = 25
        elif ratio <= 0.7:
            expense_points = 18
        elif ratio <= 0.9:
            expense_points = 10
        elif ratio <= 1.0:
            expense_points = 5
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
            consistency_points = 15
        elif positive_months == 2:
            consistency_points = 10
        elif positive_months == 1:
            consistency_points = 5
        else:
            consistency_points = 0

        cur.execute(
            f"""
            SELECT COUNT(DISTINCT t.category) FROM transactions t
            WHERE t.user_id = %s AND t.type = 'DEBIT'
              AND EXTRACT(MONTH FROM t.transaction_date)::int = %s
              AND EXTRACT(YEAR FROM t.transaction_date)::int = %s
              AND ({scope});
            """,
            (user_id, month, year),
        )
        ncat = int(cur.fetchone()[0] or 0)
        if ncat >= 5:
            diversity_points = 10
        elif ncat == 4:
            diversity_points = 7
        elif ncat == 3:
            diversity_points = 4
        else:
            diversity_points = 0

        score = int(
            min(
                100,
                savings_points + anomaly_points + expense_points + consistency_points + diversity_points,
            )
        )
        if total_income <= 0:
            score = min(score, 50)

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
        }

        weakest = min(
            [
                ("savings rate", savings_points, 30),
                ("anomaly activity", anomaly_points, 20),
                ("expense control", expense_points, 25),
                ("savings consistency", consistency_points, 15),
                ("category balance", diversity_points, 10),
            ],
            key=lambda x: x[1] / max(x[2], 1),
        )
        recs: list[str] = []
        label = weakest[0]
        if label == "savings rate":
            recs.append("Try moving at least 10% of income to savings on salary day via auto-debit SIP.")
            recs.append("Review discretionary categories (food, shopping) for quick wins.")
        elif label == "anomaly activity":
            recs.append("Review flagged transactions in the app and mark legitimate ones to reduce noise.")
            recs.append("Enable transaction alerts from your bank for real-time verification.")
        elif label == "expense control":
            recs.append("Aim to keep monthly debits below 70% of income; set a weekly spend cap.")
            recs.append("Renegotiate subscriptions and utility plans where possible.")
        elif label == "savings consistency":
            recs.append("Build a 3-month streak: even small positive savings each month improves this score.")
        else:
            recs.append("Spread essential spend across categories to avoid over-concentration risk.")
        recs.append("Track weekly UPI totals so surprises do not compound at month-end.")

        return HealthScoreResponse(
            score=score,
            grade=_grade(score),
            components=components,
            trend=trend,
            recommendations=recs[:6],
            savings_rate=savings_rate,
        )
    finally:
        cur.close()
