"""Transaction listing, summary, and CSV upload."""

from __future__ import annotations

import io
from datetime import date, datetime
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from db import get_db
from models.schemas import TransactionResponse
from services.dashboard_scope import resolve_scope_mode, transaction_scope_sql
from services.ml_model import ml_detector
from services.categorizer import category_filter_sql, normalize_category
from services.transaction_upsert import enrich_transaction_row

router = APIRouter(prefix="/transactions", tags=["transactions"])

# Register static sub-paths before `/{user_id}` so they are not captured as user ids.


def _category_filter_sql(category: str, alias: str = "t") -> tuple[str, list]:
    """Build SQL fragment for UI category chip (all legacy + snake_case aliases)."""
    return category_filter_sql(category, alias=alias)


def _anomaly_filter_sql(alias: str = "t") -> str:
    """Rows flagged by ML pipeline or high fraud-risk score."""
    return (
        f" AND (COALESCE({alias}.anomaly_flag, FALSE) = TRUE"
        f" OR COALESCE({alias}.risk_score, 0) >= 60"
        f" OR UPPER(COALESCE({alias}.risk_level, 'LOW')) IN ('HIGH', 'CRITICAL'))"
    )


def _row_to_tx(row) -> TransactionResponse:
    return TransactionResponse(
        id=row[0],
        user_id=row[1],
        transaction_date=row[2],
        transaction_time=row[3],
        amount=float(row[4]),
        type=row[5],
        description=row[6],
        merchant=row[7],
        category=row[8],
        payment_method=row[9],
        anomaly_flag=bool(row[10]),
        risk_score=int(row[11] or 0),
        risk_level=row[12] or "LOW",
        anomaly_reason=row[13],
    )


def _row_to_tx_with_source(row) -> TransactionResponse:
    """Like _row_to_tx but also reads source_name (col 14) and source_type (col 15)."""
    return TransactionResponse(
        id=row[0],
        user_id=row[1],
        transaction_date=row[2],
        transaction_time=row[3],
        amount=float(row[4]),
        type=row[5],
        description=row[6],
        merchant=row[7],
        category=row[8],
        payment_method=row[9],
        anomaly_flag=bool(row[10]),
        risk_score=int(row[11] or 0),
        risk_level=row[12] or "LOW",
        anomaly_reason=row[13],
        source_name=row[14] if len(row) > 14 else None,
        source_type=row[15] if len(row) > 15 else None,
    )


@router.get("/{user_id}/summary")
def transaction_month_summary(
    user_id: int,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    scope: Optional[str] = Query(
        None,
        description="bank_only | credit_card_only | merged",
    ),
    conn=Depends(get_db),
):
    """Month-scoped totals for the Transactions KPI. Defaults to current calendar month."""
    today = date.today()
    if month is None or year is None:
        m, y = today.month, today.year
    else:
        m, y = month, year
    cur = None
    try:
        cur = conn.cursor()
        mode = resolve_scope_mode(cur, user_id, scope)
        scope_sql = transaction_scope_sql("transactions", mode)
        cur.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN type = 'CREDIT' THEN amount ELSE 0 END), 0)::float,
                COALESCE(SUM(CASE WHEN type = 'DEBIT' THEN amount ELSE 0 END), 0)::float,
                COUNT(*)::bigint,
                COUNT(*) FILTER (WHERE COALESCE(anomaly_flag, FALSE))::bigint
            FROM transactions
            WHERE user_id = %s
              AND EXTRACT(MONTH FROM transaction_date)::int = %s
              AND EXTRACT(YEAR FROM transaction_date)::int = %s
              AND ({scope_sql});
            """,
            (user_id, m, y),
        )
        row = cur.fetchone()
        inc, exp, cnt, anom = row[0], row[1], row[2], row[3]
        saved = float(inc or 0) - float(exp or 0)
        cnt_i = int(cnt or 0)
        anom_i = int(anom or 0)
        fraud_blocked = 0
        try:
            cur.execute(
                """
                SELECT COUNT(*)::bigint FROM fraud_alerts
                WHERE user_id = %s
                  AND user_action = 'BLOCKED'
                  AND EXTRACT(MONTH FROM created_at)::int = %s
                  AND EXTRACT(YEAR FROM created_at)::int = %s;
                """,
                (user_id, m, y),
            )
            fraud_blocked = int(cur.fetchone()[0] or 0)
        except Exception:
            fraud_blocked = 0
        return {
            "user_id": user_id,
            "year": y,
            "month": m,
            "total_income": float(inc or 0),
            "total_expense": float(exp or 0),
            "saved": round(saved, 2),
            "transaction_count": cnt_i,
            "total_count": cnt_i,
            "count": cnt_i,
            "anomalies_flagged": anom_i,
            "flagged_count": anom_i,
            "fraud_blocked": fraud_blocked,
        }
    except Exception as e:
        raise HTTPException(500, f"Database error: {e}") from e
    finally:
        if cur is not None:
            cur.close()


@router.get("/{user_id}")
def list_transactions(
    user_id: int,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    category: Optional[str] = Query(None),
    anomaly_only: Optional[bool] = Query(None),
    connected_source_id: Optional[int] = Query(None, ge=1),
    uploaded_document_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    scope: Optional[str] = Query(
        None,
        description="bank_only | credit_card_only | merged",
    ),
    conn=Depends(get_db),
):
    """Transaction list — mode-aware, includes source_name/source_type for badges."""
    cur = None
    try:
        cur = conn.cursor()
        mode = resolve_scope_mode(cur, user_id, scope)
        scope_sql = transaction_scope_sql("t", mode)
        q = f"""
            SELECT t.id, t.user_id, t.transaction_date, t.transaction_time, t.amount, t.type,
                   t.description, t.merchant, t.category, t.payment_method, t.anomaly_flag,
                   t.risk_score, t.risk_level, t.anomaly_reason,
                   src.institution_name AS source_name,
                   src.source_type      AS source_type
            FROM transactions t
            LEFT JOIN connected_sources src
                   ON src.id = t.connected_source_id AND src.user_id = t.user_id
            WHERE t.user_id = %s AND ({scope_sql})
        """
        params: list = [user_id]
        if month is not None and year is not None:
            q += " AND EXTRACT(MONTH FROM t.transaction_date)::int = %s AND EXTRACT(YEAR FROM t.transaction_date)::int = %s"
            params.extend([month, year])
        elif month is not None or year is not None:
            raise HTTPException(400, "Provide both month and year, or neither.")
        if category:
            frag, extra = _category_filter_sql(category, alias="t")
            q += frag
            params.extend(extra)
        if anomaly_only:
            q += _anomaly_filter_sql(alias="t")
        if connected_source_id is not None:
            q += " AND t.connected_source_id = %s"
            params.append(connected_source_id)
        if uploaded_document_id is not None:
            q += " AND t.uploaded_document_id = %s"
            params.append(uploaded_document_id)
        q += " ORDER BY t.transaction_date DESC, t.transaction_time DESC LIMIT %s"
        params.append(limit)
        cur.execute(q, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            d["transaction_date"] = str(d["transaction_date"])
            d["transaction_time"] = str(d["transaction_time"])
            d["anomaly_flag"] = bool(d.get("anomaly_flag"))
            d["risk_score"] = int(d.get("risk_score") or 0)
            d["risk_level"] = d.get("risk_level") or "LOW"
            d["amount"] = float(d.get("amount") or 0)
            d["category"] = normalize_category(d.get("category"))
            result.append(d)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Database error: {e}") from e
    finally:
        if cur is not None:
            cur.close()


def _parse_dt(val) -> tuple[date, datetime]:
    if pd.isna(val):
        raise ValueError("empty date")
    if isinstance(val, datetime):
        dt = val
    elif isinstance(val, date):
        dt = datetime.combine(val, datetime.min.time())
    else:
        s = str(val).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(s[:10], fmt)
                break
            except ValueError:
                continue
        else:
            dt = pd.to_datetime(s).to_pydatetime()
    d = dt.date()
    t = dt.time().replace(second=0, microsecond=0)
    return d, datetime.combine(d, t)


def _parse_time(val, fallback: datetime) -> datetime:
    if pd.isna(val) or val == "" or val is None:
        return fallback
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            tt = datetime.strptime(s[:8] if len(s) >= 8 else s, fmt).time()
            return datetime.combine(fallback.date(), tt.replace(second=0, microsecond=0))
        except ValueError:
            continue
    return fallback


@router.post("/{user_id}/upload")
async def upload_csv(user_id: int, file: UploadFile = File(...), conn=Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file")
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(400, f"Invalid CSV: {e}") from e

    colmap = {c.lower().strip(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in colmap:
                return colmap[n]
        return None

    c_date = pick("transaction_date", "date", "txn_date")
    c_time = pick("transaction_time", "time")
    c_amt = pick("amount", "debit", "credit")
    c_type = pick("type", "dr_cr", "txn_type")
    c_merch = pick("merchant", "payee", "description")
    c_desc = pick("description", "narration", "remarks")
    c_cat = pick("category")
    if not c_date or not c_amt:
        raise HTTPException(
            400,
            "CSV must include at least transaction_date (or date) and amount columns.",
        )

    inserted = 0
    cur = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
        if not cur.fetchone():
            raise HTTPException(404, "User not found")

        for _, row in df.iterrows():
            try:
                d, fallback_dt = _parse_dt(row[c_date])
                dt = _parse_time(row[c_time], fallback_dt) if c_time else fallback_dt
                amt = float(row[c_amt])
                txn_type = str(row[c_type]).upper().strip() if c_type and not pd.isna(row[c_type]) else "DEBIT"
                if txn_type not in ("DEBIT", "CREDIT"):
                    txn_type = "DEBIT"
                merchant = str(row[c_merch]).strip() if c_merch and not pd.isna(row[c_merch]) else ""
                desc = str(row[c_desc]).strip() if c_desc and not pd.isna(row[c_desc]) else None
                enriched = enrich_transaction_row(
                    {
                        "merchant": merchant or desc or "Unknown",
                        "category": (
                            str(row[c_cat]).strip()
                            if c_cat and not pd.isna(row[c_cat])
                            else None
                        ),
                    }
                )
                merchant = enriched["merchant"]
                cat = enriched["category"]
                normalized_merchant = enriched["normalized_merchant"]
                hod = dt.hour
                dow = dt.weekday()
                wknd = dow >= 5
                night = hod >= 23 or hod <= 5
                cur.execute(
                    """
                    INSERT INTO transactions (
                        user_id, transaction_date, transaction_time, amount, type, description,
                        merchant, normalized_merchant, category, subcategory, payment_method, location,
                        anomaly_flag, risk_score, risk_level, anomaly_reason, ml_processed,
                        hour_of_day, day_of_week, is_weekend, is_night_txn
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        FALSE, 0, 'LOW', NULL, FALSE,
                        %s, %s, %s, %s
                    );
                    """,
                    (
                        user_id,
                        d,
                        dt.time(),
                        amt,
                        txn_type,
                        desc,
                        merchant or None,
                        normalized_merchant,
                        cat,
                        "Imported",
                        "UPI",
                        None,
                        hod,
                        dow,
                        wknd,
                        night,
                    ),
                )
                inserted += 1
            except Exception:
                continue
        ml_detector.train(user_id)
        det = ml_detector.detect_and_update(user_id, process_all=False)
        return {
            "inserted": inserted,
            "anomalies_found": det.get("anomalies_found", 0),
            "high_risk": det.get("high_risk", 0),
            "processed": det.get("processed", 0),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {e}") from e
    finally:
        if cur is not None:
            cur.close()
