"""Spending breakdown, trends, merchants, and scenario simulation."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_db
from models.schemas import MonthlyTrend, SpendingAnalysis
from services.scorer import calculate_health_score

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _trends_rows_need_transaction_fallback(trends: list[MonthlyTrend]) -> bool:
    """
    Use live transaction aggregation when there is no summary, or summary exists
    but every stored month has zero income and zero expense (stale / placeholder rows).
    When any month has income > 0 or expense > 0, keep ``monthly_summary`` as source of truth.
    """
    if not trends:
        return True

    def _z(x: float) -> bool:
        return abs(float(x or 0)) < 1e-6

    return all(_z(t.income) and _z(t.expense) for t in trends)


def _monthly_trends_from_transactions(cur, user_id: int) -> list[MonthlyTrend]:
    """
    Last 12 calendar months ending at CURRENT_DATE (user-wide; not scoped to dashboard M/Y).
    Income = CREDIT, expense = DEBIT; saved = max(0, income - expense).
    health_score / anomaly_count from monthly_summary for that month when present, else 0.
    """
    cur.execute(
        """
        WITH bounds AS (
            SELECT
                (date_trunc('month', CURRENT_DATE::timestamp) - interval '11 months')::date AS start_m,
                date_trunc('month', CURRENT_DATE::timestamp)::date AS end_m
        ),
        months AS (
            SELECT gs::date AS month_start
            FROM generate_series(
                (SELECT start_m FROM bounds),
                (SELECT end_m FROM bounds),
                interval '1 month'
            ) AS gs
        ),
        tx AS (
            SELECT
                EXTRACT(YEAR FROM t.transaction_date)::int AS y,
                EXTRACT(MONTH FROM t.transaction_date)::int AS m,
                COALESCE(SUM(CASE WHEN t.type = 'CREDIT' THEN t.amount ELSE 0 END), 0)::float AS income,
                COALESCE(SUM(CASE WHEN t.type = 'DEBIT' THEN t.amount ELSE 0 END), 0)::float AS expense
            FROM transactions t
            WHERE t.user_id = %s
              AND t.transaction_date >= (SELECT start_m FROM bounds)
              AND t.transaction_date < ((SELECT end_m FROM bounds) + interval '1 month')
            GROUP BY EXTRACT(YEAR FROM t.transaction_date), EXTRACT(MONTH FROM t.transaction_date)
        )
        SELECT
            EXTRACT(YEAR FROM mo.month_start)::int AS year,
            EXTRACT(MONTH FROM mo.month_start)::int AS month,
            COALESCE(tx.income, 0)::float AS income,
            COALESCE(tx.expense, 0)::float AS expense,
            GREATEST(0, COALESCE(tx.income, 0) - COALESCE(tx.expense, 0))::float AS saved,
            COALESCE(ms.health_score, 0)::int AS health_score,
            COALESCE(ms.anomaly_count, 0)::int AS anomaly_count
        FROM months mo
        LEFT JOIN tx
          ON tx.y = EXTRACT(YEAR FROM mo.month_start)::int
         AND tx.m = EXTRACT(MONTH FROM mo.month_start)::int
        LEFT JOIN monthly_summary ms
          ON ms.user_id = %s
         AND ms.year = EXTRACT(YEAR FROM mo.month_start)::int
         AND ms.month = EXTRACT(MONTH FROM mo.month_start)::int
        ORDER BY year ASC, month ASC;
        """,
        (user_id, user_id),
    )
    rows = cur.fetchall()
    out: list[MonthlyTrend] = []
    for r in rows:
        y, m = int(r[0]), int(r[1])
        out.append(
            MonthlyTrend(
                month=f"{y}-{m:02d}",
                income=float(r[2] or 0),
                expense=float(r[3] or 0),
                saved=float(r[4] or 0),
                health_score=int(r[5] or 0),
                anomaly_count=int(r[6] or 0),
            )
        )
    return out


@router.get("/{user_id}/spending", response_model=list[SpendingAnalysis])
def spending_by_category(
    user_id: int,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    conn=Depends(get_db),
):
    cur = conn.cursor()
    try:
        pm, py = (month - 1, year) if month > 1 else (12, year - 1)
        cur.execute(
            """
            WITH cur AS (
                SELECT COALESCE(category, 'Uncategorized') AS category,
                       SUM(amount)::float AS total, COUNT(*)::int AS cnt
                FROM transactions
                WHERE user_id = %s AND type = 'DEBIT'
                  AND EXTRACT(MONTH FROM transaction_date)::int = %s
                  AND EXTRACT(YEAR FROM transaction_date)::int = %s
                GROUP BY 1
            ),
            prev AS (
                SELECT COALESCE(category, 'Uncategorized') AS category, SUM(amount)::float AS total
                FROM transactions
                WHERE user_id = %s AND type = 'DEBIT'
                  AND EXTRACT(MONTH FROM transaction_date)::int = %s
                  AND EXTRACT(YEAR FROM transaction_date)::int = %s
                GROUP BY 1
            )
            SELECT cur.category, cur.total, cur.cnt, COALESCE(prev.total, 0)::float
            FROM cur LEFT JOIN prev ON prev.category = cur.category;
            """,
            (user_id, month, year, user_id, pm, py),
        )
        rows = cur.fetchall()
        grand = sum(r[1] or 0 for r in rows) or 1.0
        out: list[SpendingAnalysis] = []
        for cat, total, cnt, prev_total in rows:
            total_f = float(total or 0)
            prev_f = float(prev_total or 0)
            if prev_f <= 0 and total_f > 0:
                trend = "UP"
            elif total_f > prev_f * 1.05:
                trend = "UP"
            elif total_f < prev_f * 0.95 and prev_f > 0:
                trend = "DOWN"
            else:
                trend = "STABLE"
            out.append(
                SpendingAnalysis(
                    category=cat,
                    total_amount=round(total_f, 2),
                    transaction_count=int(cnt or 0),
                    percentage=round(total_f / grand * 100, 2),
                    avg_transaction=round(total_f / max(cnt, 1), 2),
                    trend=trend,
                )
            )
        out.sort(key=lambda x: x.total_amount, reverse=True)
        return out
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()


@router.get("/{user_id}/trends", response_model=list[MonthlyTrend])
def monthly_trends(user_id: int, conn=Depends(get_db)):
    """
    Rolling last-12-month series (newest month = current calendar month in DB session).
    Prefers ``monthly_summary``; if empty or all income/expense are zero, aggregates from
    ``transactions`` so demos work when summary was never backfilled. Dashboard month/year
    filters do not apply here — spending pie remains month-scoped via ``/spending``.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT year, month, total_income::float, total_expense::float, total_saved::float,
                   COALESCE(health_score, 0), COALESCE(anomaly_count, 0)
            FROM monthly_summary
            WHERE user_id = %s
            ORDER BY year DESC, month DESC
            LIMIT 12;
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        out: list[MonthlyTrend] = []
        for r in rows:
            y, m = int(r[0]), int(r[1])
            out.append(
                MonthlyTrend(
                    month=f"{y}-{m:02d}",
                    income=float(r[2] or 0),
                    expense=float(r[3] or 0),
                    saved=float(r[4] or 0),
                    health_score=int(r[5] or 0),
                    anomaly_count=int(r[6] or 0),
                )
            )
        summary_series = list(reversed(out))
        if _trends_rows_need_transaction_fallback(summary_series):
            return _monthly_trends_from_transactions(cur, user_id)
        return summary_series
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()


@router.get("/{user_id}/merchants")
def top_merchants(
    user_id: int,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    conn=Depends(get_db),
):
    today = date.today()
    m = month or today.month
    y = year or today.year
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT merchant, SUM(amount)::float AS s
            FROM transactions
            WHERE user_id = %s AND type = 'DEBIT'
              AND EXTRACT(MONTH FROM transaction_date)::int = %s
              AND EXTRACT(YEAR FROM transaction_date)::int = %s
              AND merchant IS NOT NULL AND merchant <> ''
            GROUP BY merchant
            ORDER BY s DESC
            LIMIT 10;
            """,
            (user_id, m, y),
        )
        return [{"merchant": r[0], "total_spend": round(float(r[1]), 2)} for r in cur.fetchall()]
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()


@router.get("/{user_id}/simulate")
def simulate_scenario(
    user_id: int,
    scenario_type: str = Query(..., pattern="^(increase_spending|decrease_income|add_savings)$"),
    percentage: int = Query(20, ge=1, le=100),
    conn=Depends(get_db),
):
    cur = conn.cursor()
    try:
        today = date.today()
        m, y = today.month, today.year
        cur.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN type = 'CREDIT' THEN amount ELSE 0 END), 0)::float,
                   COALESCE(SUM(CASE WHEN type = 'DEBIT' THEN amount ELSE 0 END), 0)::float
            FROM transactions
            WHERE user_id = %s
              AND EXTRACT(MONTH FROM transaction_date)::int = %s
              AND EXTRACT(YEAR FROM transaction_date)::int = %s;
            """,
            (user_id, m, y),
        )
        inc, exp = cur.fetchone()
        inc, exp = float(inc or 0), float(exp or 0)
        base = calculate_health_score(conn, user_id, m, y)
        base_score = base.score
        p = percentage / 100.0
        if scenario_type == "increase_spending":
            new_exp = exp * (1 + p)
            ratio = new_exp / inc if inc > 0 else 2.0
            proj_health = max(0, int(base_score - 15 * p * 10))
            proj_savings = max(0.0, inc - new_exp)
            impact = f"Raising debits by {percentage}% pushes expense/income to ~{ratio:.2f}."
        elif scenario_type == "decrease_income":
            new_inc = inc * (1 - p)
            ratio = exp / new_inc if new_inc > 0 else 2.0
            proj_health = max(0, int(base_score - 20 * p * 10))
            proj_savings = max(0.0, new_inc - exp)
            impact = f"Income down {percentage}% worsens cushion; expense/income ~{ratio:.2f}."
        else:
            new_exp = exp * (1 - p * 0.5)
            proj_health = min(100, int(base_score + 12 * p * 5))
            proj_savings = max(0.0, inc - new_exp)
            impact = f"Cutting discretionary spend ~{percentage//2}% improves headroom."
        rec = base.recommendations[:2]
        return {
            "scenario_type": scenario_type,
            "percentage": percentage,
            "current_health_score": base_score,
            "projected_health_score": proj_health,
            "projected_monthly_savings_inr": round(proj_savings, 2),
            "impact_analysis": impact,
            "recommendations": rec,
        }
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()
