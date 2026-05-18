"""Dashboard-specific endpoints: source breakdown and deduplication."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_db

from services.dashboard_scope import resolve_scope_mode, transaction_scope_sql

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/source-breakdown")
def get_source_breakdown(
    user_id: int,
    scope: Optional[str] = Query(
        None,
        description="bank_only | credit_card_only | merged",
    ),
    db=Depends(get_db),
):
    """
    Spending split by source type for the current calendar month.
    Returns bank vs credit-card breakdown + total spend + duplicate flag.
    """
    cur = None
    try:
        cur = db.cursor()
        mode = resolve_scope_mode(cur, user_id, scope)
        scope_sql = transaction_scope_sql("t", mode)

        cur.execute(
            f"""
            SELECT
                COALESCE(cs.source_type, 'bank')            AS source_type,
                COALESCE(cs.institution_name, 'Bank Account') AS source_name,
                COALESCE(
                    SUM(CASE
                        WHEN t.type = 'DEBIT'
                             AND COALESCE(t.category, '') != 'internal_transfer'
                        THEN t.amount ELSE 0
                    END), 0
                )::float                                    AS spend
            FROM transactions t
            LEFT JOIN connected_sources cs
                   ON cs.id = t.connected_source_id AND cs.user_id = t.user_id
            WHERE t.user_id = %s
              AND ({scope_sql})
              AND t.transaction_date >= DATE_TRUNC('month', CURRENT_DATE)
              AND t.transaction_date  < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
            GROUP BY source_type, source_name
            HAVING SUM(CASE WHEN t.type = 'DEBIT' THEN t.amount ELSE 0 END) > 0
            ORDER BY spend DESC
            """,
            (user_id,),
        )

        sources = []
        total_spend = 0.0
        for row in cur.fetchall():
            spend = float(row[2] or 0)
            sources.append({"type": row[0], "name": row[1], "spend": spend})
            total_spend += spend

        # Detect potential CC bill payments in bank transactions that
        # haven't been marked internal_transfer yet.
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM transactions t
            LEFT JOIN connected_sources cs
                   ON cs.id = t.connected_source_id AND cs.user_id = t.user_id
            WHERE t.user_id = %s
              AND ({scope_sql})
              AND t.type = 'DEBIT'
              AND COALESCE(t.category, '') != 'internal_transfer'
              AND (
                LOWER(COALESCE(t.merchant, ''))     LIKE '%%credit card%%'
                OR LOWER(COALESCE(t.merchant, ''))  LIKE '%%cc payment%%'
                OR LOWER(COALESCE(t.description, '')) LIKE '%%credit card payment%%'
              )
            """,
            (user_id,),
        )
        potential_dups = int((cur.fetchone() or [0])[0])

        return {
            "mode": mode,
            "sources": sources,
            "total_spend": round(total_spend, 2),
            "has_duplicates": potential_dups > 0,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Breakdown error: {e}") from e
    finally:
        if cur is not None:
            cur.close()


@router.post("/deduplicate")
def run_deduplication(user_id: int, db=Depends(get_db)):
    """
    Detect and mark credit-card bill payments from bank accounts as
    'internal_transfer' so they are excluded from total-spend calculations
    in merged view.
    """
    cur = None
    try:
        cur = db.cursor()
        cur.execute(
            """
            UPDATE transactions t1
            SET category = 'internal_transfer'
            WHERE t1.user_id = %s
              AND t1.type = 'DEBIT'
              AND COALESCE(t1.category, '') != 'internal_transfer'
              AND (
                LOWER(COALESCE(t1.merchant, ''))      LIKE '%%credit card%%'
                OR LOWER(COALESCE(t1.merchant, ''))   LIKE '%%cc payment%%'
                OR LOWER(COALESCE(t1.description, '')) LIKE '%%credit card payment%%'
              )
              AND EXISTS (
                SELECT 1 FROM transactions t2
                WHERE t2.user_id = t1.user_id
                  AND t2.type = 'CREDIT'
                  AND ABS(t2.amount - t1.amount) < 10
                  AND ABS(
                    EXTRACT(EPOCH FROM (t2.transaction_date::timestamp - t1.transaction_date::timestamp))
                  ) < 172800
                  AND t2.connected_source_id IS DISTINCT FROM t1.connected_source_id
              )
            """,
            (user_id,),
        )
        marked = cur.rowcount
        db.commit()
        return {
            "success": True,
            "marked_as_internal": marked,
            "message": f"Marked {marked} transaction(s) as internal transfers",
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Deduplication error: {e}") from e
    finally:
        if cur is not None:
            cur.close()
