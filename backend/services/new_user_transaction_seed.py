"""Insert synthetic transaction history for newly registered users (demo / local)."""

from __future__ import annotations

import calendar
import logging
import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)

MERCHANTS = [
    "Amazon India",
    "Flipkart",
    "Swiggy",
    "Zomato",
    "BigBasket",
    "Myntra",
    "Nykaa",
    "BookMyShow",
    "Ola",
    "Uber",
    "PhonePe",
    "IRCTC",
    "MakeMyTrip",
    "Paytm",
    "Jio Recharge",
    "Zepto",
    "Blinkit",
    "Meesho",
    "Dunzo",
    "Netflix",
    "Spotify",
    "Croma",
    "Reliance Smart",
    "Apollo Pharmacy",
]

CATEGORIES = ["Shopping", "Food", "Transport", "Entertainment", "Recharge", "Health", "Utilities", "Groceries"]
LOCATIONS = ["Mumbai", "Delhi", "Bangalore", "Chennai", "Hyderabad", "Pune", "Kolkata", "Ahmedabad"]

# At least 1000 rows spanning 2 years (730 days). ~45% in the anchor month so MTD KPIs are populated.
DEFAULT_COUNT = 1100
DEFAULT_SPAN_DAYS = 730
FRACTION_IN_ANCHOR_MONTH = 0.45


def _fetch_transaction_columns(cur: Any) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'transactions'
        """
    )
    return {str(r[0]) for r in cur.fetchall()}


def _build_row(
    cols: set[str],
    rnd: random.Random,
    *,
    user_id: int,
    txn_dt: datetime,
    amount: float,
    merchant: str,
    category: str,
    txn_type: str,
    description: str | None = None,
) -> dict[str, Any]:
    hod = int(txn_dt.hour)
    dow = int(txn_dt.weekday())
    is_weekend = dow >= 5
    is_night = hod >= 23 or hod < 5
    row: dict[str, Any] = {}
    if "user_id" in cols:
        row["user_id"] = user_id
    if "transaction_date" in cols:
        row["transaction_date"] = txn_dt.date()
    if "transaction_time" in cols:
        row["transaction_time"] = txn_dt.time()
    if "created_at" in cols:
        row["created_at"] = txn_dt.replace(tzinfo=timezone.utc)
    if "amount" in cols:
        row["amount"] = amount
    if "type" in cols:
        row["type"] = txn_type
    if "description" in cols:
        row["description"] = (
            description if description is not None else f"{merchant} — {category}"
        )
    if "merchant" in cols:
        row["merchant"] = merchant
    if "category" in cols:
        row["category"] = category
    if "subcategory" in cols:
        row["subcategory"] = "General"
    if "payment_method" in cols:
        row["payment_method"] = rnd.choice(["UPI", "CARD", "NETBANKING", "WALLET"])
    if "location" in cols:
        row["location"] = rnd.choice(LOCATIONS)
    if "bank_name" in cols:
        row["bank_name"] = "SmartSpend Demo"
    if "balance_after" in cols:
        row["balance_after"] = round(rnd.uniform(5000, 250000), 2)
    if "anomaly_flag" in cols:
        row["anomaly_flag"] = False
    if "risk_score" in cols:
        row["risk_score"] = 0
    if "risk_level" in cols:
        row["risk_level"] = "LOW"
    if "anomaly_reason" in cols:
        row["anomaly_reason"] = None
    if "ml_processed" in cols:
        row["ml_processed"] = False
    if "hour_of_day" in cols:
        row["hour_of_day"] = hod
    if "day_of_week" in cols:
        row["day_of_week"] = dow
    if "is_weekend" in cols:
        row["is_weekend"] = is_weekend
    if "is_night_txn" in cols:
        row["is_night_txn"] = is_night
    if "is_fraud" in cols:
        row["is_fraud"] = False
    return row


def seed_transactions_for_new_user(
    cur: Any,
    user_id: int,
    *,
    count: int = DEFAULT_COUNT,
    span_days: int = DEFAULT_SPAN_DAYS,
    anchor_date: date | None = None,
) -> int:
    """
    Bulk-insert ``count`` synthetic transactions for ``user_id``.

    - ~45% of rows fall on random days in the **anchor month** (default: today), so dashboard
      month views show non-zero spend immediately.
    - The rest are spread uniformly over the last ``span_days`` days.
    """
    cols = _fetch_transaction_columns(cur)
    if not cols or "user_id" not in cols:
        logger.warning("transactions table missing expected columns; skip seed for user_id=%s", user_id)
        return 0

    anchor = anchor_date or date.today()
    start = anchor - timedelta(days=span_days)
    rnd = random.Random(int(user_id) * 7919 + 42)

    n_anchor = max(1, min(count - 1, int(round(count * FRACTION_IN_ANCHOR_MONTH))))
    n_rest = count - n_anchor
    yr, mo = anchor.year, anchor.month
    _, dim = calendar.monthrange(yr, mo)

    rows_dicts: list[dict[str, Any]] = []

    for _ in range(n_anchor):
        d = date(yr, mo, rnd.randint(1, dim))
        txn_dt = datetime.combine(
            d,
            time(
                hour=rnd.randint(6, 23),
                minute=rnd.randint(0, 59),
                second=rnd.randint(0, 59),
            ),
        )
        merchant = rnd.choice(MERCHANTS)
        category = rnd.choice(CATEGORIES)
        is_credit = rnd.random() < 0.08
        txn_type = "CREDIT" if is_credit else "DEBIT"
        amount = (
            round(rnd.uniform(500, 45000), 2) if is_credit else round(rnd.uniform(29, 12000), 2)
        )
        rows_dicts.append(
            _build_row(
                cols,
                rnd,
                user_id=user_id,
                txn_dt=txn_dt,
                amount=amount,
                merchant=merchant,
                category=category,
                txn_type=txn_type,
            )
        )

    for _ in range(n_rest):
        offset_days = rnd.randint(0, span_days)
        d = start + timedelta(days=offset_days)
        txn_dt = datetime.combine(
            d,
            time(
                hour=rnd.randint(6, 23),
                minute=rnd.randint(0, 59),
                second=rnd.randint(0, 59),
            ),
        )
        merchant = rnd.choice(MERCHANTS)
        category = rnd.choice(CATEGORIES)
        is_credit = rnd.random() < 0.08
        txn_type = "CREDIT" if is_credit else "DEBIT"
        amount = (
            round(rnd.uniform(500, 45000), 2) if is_credit else round(rnd.uniform(29, 12000), 2)
        )
        rows_dicts.append(
            _build_row(
                cols,
                rnd,
                user_id=user_id,
                txn_dt=txn_dt,
                amount=amount,
                merchant=merchant,
                category=category,
                txn_type=txn_type,
            )
        )

    if not rows_dicts:
        return 0

    column_order = sorted(rows_dicts[0].keys())
    tuples = [tuple(r[c] for c in column_order) for r in rows_dicts]
    col_sql = ", ".join(column_order)
    template = "(" + ", ".join(["%s"] * len(column_order)) + ")"
    sql = f"INSERT INTO transactions ({col_sql}) VALUES %s"

    execute_values(cur, sql, tuples, template=template, page_size=400)
    logger.info(
        "Inserted %s synthetic transactions for user_id=%s (anchor=%s-%02d, span_days=%s)",
        count,
        user_id,
        yr,
        mo,
        span_days,
    )
    return count


def insert_individual_transactions(
    cur: Any,
    user_id: int,
    items: list[dict[str, Any]],
) -> int:
    """
    Insert explicit rows (EMI cadence, subscriptions, trial traps, etc.).

    Each item: ``transaction_date`` (date), ``amount``, ``merchant``, ``category``,
    ``type`` (DEBIT/CREDIT, default DEBIT), optional ``transaction_time`` (time),
    optional ``description``.
    """
    if not items:
        return 0
    cols = _fetch_transaction_columns(cur)
    if not cols or "user_id" not in cols:
        logger.warning("insert_individual_transactions: missing transactions columns")
        return 0
    rnd = random.Random(int(user_id) * 7919 + 101)
    rows_dicts: list[dict[str, Any]] = []
    for spec in items:
        d = spec["transaction_date"]
        if not isinstance(d, date):
            raise TypeError("transaction_date must be a datetime.date")
        tm = spec.get("transaction_time") or time(10, 15, 0)
        txn_dt = datetime.combine(d, tm)
        rows_dicts.append(
            _build_row(
                cols,
                rnd,
                user_id=user_id,
                txn_dt=txn_dt,
                amount=float(spec["amount"]),
                merchant=str(spec["merchant"]),
                category=str(spec.get("category") or "General"),
                txn_type=str(spec.get("type") or "DEBIT"),
                description=spec.get("description"),
            )
        )
    column_order = sorted(rows_dicts[0].keys())
    tuples = [tuple(r[c] for c in column_order) for r in rows_dicts]
    col_sql = ", ".join(column_order)
    template = "(" + ", ".join(["%s"] * len(column_order)) + ")"
    sql = f"INSERT INTO transactions ({col_sql}) VALUES %s"
    execute_values(cur, sql, tuples, template=template, page_size=200)
    logger.info("Inserted %s individual pattern transactions for user_id=%s", len(rows_dicts), user_id)
    return len(rows_dicts)


def bulk_insert_transaction_dicts(cur: Any, rows: list[dict[str, Any]]) -> int:
    """
    Insert rows that already match ``transactions`` column names (e.g. from corpus materializer).
    All dicts must share the same key set.
    """
    if not rows:
        return 0
    column_order = sorted(rows[0].keys())
    for i, r in enumerate(rows[1:], start=1):
        if sorted(r.keys()) != column_order:
            raise ValueError(f"transaction row {i} keys mismatch vs first row")
    tuples = [tuple(r[c] for c in column_order) for r in rows]
    col_sql = ", ".join(column_order)
    template = "(" + ", ".join(["%s"] * len(column_order)) + ")"
    sql = f"INSERT INTO transactions ({col_sql}) VALUES %s"
    execute_values(cur, sql, tuples, template=template, page_size=500)
    logger.info("bulk_insert_transaction_dicts inserted %s rows", len(rows))
    return len(rows)


def ensure_user_has_transactions(
    cur: Any,
    user_id: int,
    *,
    min_count: int = DEFAULT_COUNT,
    span_days: int = DEFAULT_SPAN_DAYS,
    anchor_date: date | None = None,
) -> int:
    """If the user has fewer than ``min_count`` transactions, insert enough to reach ``min_count``."""
    cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id = %s", (user_id,))
    existing = int(cur.fetchone()[0] or 0)
    if existing >= min_count:
        logger.info("user_id=%s already has %s transactions (>= %s); skip seed", user_id, existing, min_count)
        return 0
    need = min_count - existing
    return seed_transactions_for_new_user(
        cur, user_id, count=need, span_days=span_days, anchor_date=anchor_date
    )
