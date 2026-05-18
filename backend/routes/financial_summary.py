"""Unified financial summary for EMI ↔ Festival ↔ Purchase Planner."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_db
from routes.emi_detector import _infer_monthly_income
from services.dashboard_scope import resolve_scope_mode, transaction_scope_sql

router = APIRouter(prefix="/financial-summary", tags=["financial-summary"])


@router.get("/{user_id}")
def get_financial_summary(
    user_id: int,
    scope: Optional[str] = Query(
        None,
        description="bank_only | credit_card_only | merged (defaults to user dashboard_mode)",
    ),
    conn=Depends(get_db),
) -> dict[str, Any]:
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(404, "User not found")

        mode = resolve_scope_mode(cur, user_id, scope)
        scope_sql = transaction_scope_sql("t", mode)

        cur.execute(
            "SELECT COALESCE(monthly_income, 0)::float FROM users WHERE id = %s",
            (user_id,),
        )
        income = float((cur.fetchone() or [0])[0] or 0)
        if income <= 0:
            income = _infer_monthly_income(cur, user_id, mode)

        cur.execute(
            """
            SELECT merchant, detected_amount, emi_type, is_active, next_due_date
            FROM emi_records
            WHERE user_id = %s AND COALESCE(is_active, TRUE) = TRUE
            ORDER BY detected_amount DESC
            """,
            (user_id,),
        )
        emi_rows = cur.fetchall()
        active_emis = [
            {
                "merchant": r[0],
                "monthly_amount": float(r[1] or 0),
                "emi_type": r[2],
                "status": "active",
                "next_due": str(r[4]) if r[4] else None,
            }
            for r in emi_rows
        ]
        monthly_emi_total = sum(e["monthly_amount"] for e in active_emis)

        festival_reserved = 0.0
        try:
            cur.execute(
                """
                SELECT COALESCE(SUM(COALESCE(monthly_target, 0)), 0)::float
                FROM festival_budgets
                WHERE user_id = %s
                  AND festival_date >= CURRENT_DATE
                """,
                (user_id,),
            )
            festival_reserved = float((cur.fetchone() or [0])[0] or 0)
        except Exception:
            festival_reserved = 0.0

        projected_monthly = 0.0
        try:
            cur.execute(
                """
                SELECT COALESCE(SUM(COALESCE(monthly_target, 0)), 0)::float
                FROM purchase_goals
                WHERE user_id = %s
                  AND UPPER(COALESCE(status, 'ACTIVE')) NOT IN ('COMPLETED', 'CANCELLED', 'PAUSED')
                """,
                (user_id,),
            )
            projected_monthly = float((cur.fetchone() or [0])[0] or 0)
        except Exception:
            projected_monthly = 0.0

        available = max(
            0.0,
            income - monthly_emi_total - festival_reserved - projected_monthly,
        )

        return {
            "monthly_income": round(income, 2),
            "monthly_emi_total": round(monthly_emi_total, 2),
            "active_emis": active_emis,
            "festival_reserved": round(festival_reserved, 2),
            "projected_monthly_emi": round(projected_monthly, 2),
            "available_for_purchase": round(available, 2),
            "mode": mode,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, "Could not load financial summary") from exc
    finally:
        cur.close()
