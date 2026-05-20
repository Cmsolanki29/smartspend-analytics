"""Health score API."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_db
from models.schemas import HealthScoreResponse
from services.openai_service import invalidate_insight_cache
from services.scorer import calculate_health_score, refresh_user_health_score

router = APIRouter(prefix="/health-score", tags=["health-score"])


@router.get("/{user_id}", response_model=HealthScoreResponse)
def get_health_score(
    user_id: int,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    scope: Optional[str] = Query(
        None,
        description="bank_only | credit_card_only | merged | all (defaults to user dashboard_mode)",
    ),
    force: bool = Query(False, description="Invalidate insight cache before recalculating"),
    conn=Depends(get_db),
):
    today = date.today()
    m = month or today.month
    y = year or today.year
    try:
        if force:
            invalidate_insight_cache(conn, user_id, m, y, scope)
        return calculate_health_score(conn, user_id, m, y, scope=scope)
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@router.post("/{user_id}/refresh")
def refresh_health_score(
    user_id: int,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    scope: Optional[str] = Query(
        None,
        description="bank_only | credit_card_only | merged | all",
    ),
    conn=Depends(get_db),
):
    """Recalculate health from live DB after EMI / planner / festival changes."""
    today = date.today()
    m = month or today.month
    y = year or today.year
    try:
        return refresh_user_health_score(conn, user_id, m, y, scope=scope)
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@router.get("/{user_id}/history")
def health_history(user_id: int, conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT year, month, COALESCE(health_score, 0)
            FROM monthly_summary
            WHERE user_id = %s
            ORDER BY year DESC, month DESC
            LIMIT 12;
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        return [{"year": int(r[0]), "month": int(r[1]), "health_score": int(r[2])} for r in reversed(rows)]
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    finally:
        cur.close()
