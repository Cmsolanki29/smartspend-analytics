"""Assign corpus templates to a user's ``transactions`` table."""

from __future__ import annotations

import calendar
import logging
import random
from datetime import date, datetime, time, timedelta
from typing import Any

from services.indian_fintech_seed.personas import PERSONAS
from services.new_user_transaction_seed import _build_row, _fetch_transaction_columns, bulk_insert_transaction_dicts

logger = logging.getLogger(__name__)


def upsert_personas(cur: Any) -> int:
    """Insert or update static personas from ``personas.PERSONAS``."""
    n = 0
    for p in PERSONAS:
        cur.execute(
            """
            INSERT INTO user_personas (
              persona_key, name, age, occupation, city, city_tier, monthly_income, lifestyle, age_group,
              has_home_loan, home_loan_emi, has_vehicle_loan, vehicle_loan_emi, has_personal_loan, personal_loan_emi,
              food_delivery_freq, shopping_style, subscription_count
            ) VALUES (
              %(persona_key)s, %(name)s, %(age)s, %(occupation)s, %(city)s, %(city_tier)s, %(monthly_income)s,
              %(lifestyle)s, %(age_group)s, %(has_home_loan)s, %(home_loan_emi)s, %(has_vehicle_loan)s,
              %(vehicle_loan_emi)s, %(has_personal_loan)s, %(personal_loan_emi)s, %(food_delivery_freq)s,
              %(shopping_style)s, %(subscription_count)s
            )
            ON CONFLICT (persona_key) DO UPDATE SET
              name = EXCLUDED.name,
              age = EXCLUDED.age,
              occupation = EXCLUDED.occupation,
              city = EXCLUDED.city,
              city_tier = EXCLUDED.city_tier,
              monthly_income = EXCLUDED.monthly_income,
              lifestyle = EXCLUDED.lifestyle,
              age_group = EXCLUDED.age_group,
              has_home_loan = EXCLUDED.has_home_loan,
              home_loan_emi = EXCLUDED.home_loan_emi,
              has_vehicle_loan = EXCLUDED.has_vehicle_loan,
              vehicle_loan_emi = EXCLUDED.vehicle_loan_emi,
              has_personal_loan = EXCLUDED.has_personal_loan,
              personal_loan_emi = EXCLUDED.personal_loan_emi,
              food_delivery_freq = EXCLUDED.food_delivery_freq,
              shopping_style = EXCLUDED.shopping_style,
              subscription_count = EXCLUDED.subscription_count;
            """,
            p,
        )
        n += 1
    return n


def _month_series(start: date, end: date, day_of_month: int) -> list[date]:
    out: list[date] = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        dim = calendar.monthrange(cur.year, cur.month)[1]
        cand = date(cur.year, cur.month, min(day_of_month, dim))
        if cand >= start and cand <= end:
            out.append(cand)
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return out


def _random_day_in_range(rnd: random.Random, start: date, end: date) -> date:
    span = (end - start).days
    if span <= 0:
        return end
    return start + timedelta(days=rnd.randint(0, span))


def _map_category(seed_cat: str, sub: str | None) -> str:
    s = (seed_cat or "General").upper()
    if s in ("FOOD", "FESTIVAL"):
        return "Food"
    if s == "TRANSPORT":
        return "Transport"
    if s == "SHOPPING":
        return "Shopping"
    if s in ("SUBSCRIPTION", "ENTERTAINMENT"):
        return "Entertainment"
    if s == "UTILITY":
        return "Utilities"
    if s == "HEALTH":
        return "Health"
    if s == "INCOME":
        return "Salary" if (sub or "").lower() == "salary" else "Income"
    if s == "EMI":
        return "Finance"
    if s == "FRAUD":
        return "Shopping"
    if s == "MISC":
        return (sub or "General")[:50] if sub else "General"
    return s[:50] if s else "General"


def _should_expand_monthly(t: dict[str, Any]) -> bool:
    if (t.get("frequency") or "").lower() != "monthly":
        return False
    if t.get("is_emi") or t.get("is_subscription"):
        return True
    cat = (t.get("category") or "").lower()
    sub = (t.get("subcategory") or "").lower()
    return cat == "income" and sub == "salary"


def _template_to_txn_rows(
    t: dict[str, Any],
    *,
    user_id: int,
    cols: set[str],
    rnd: random.Random,
    window_start: date,
    window_end: date,
    max_monthly: int,
) -> list[dict[str, Any]]:
    merchant = str(t.get("merchant_name") or "Unknown")
    desc = str(t.get("description") or merchant)
    typ = str(t.get("transaction_type") or "DEBIT").upper()
    if typ not in ("DEBIT", "CREDIT"):
        typ = "DEBIT"
    amt = float(t.get("amount") or 0)
    cat = _map_category(str(t.get("category") or ""), t.get("subcategory"))
    dom = t.get("day_of_month")
    th = t.get("typical_hour")
    hour = int(th) if th is not None else rnd.randint(9, 21)
    minute = rnd.randint(0, 56)

    if t.get("is_fraud_pattern") and (t.get("fraud_type") or "").lower() == "duplicate":
        d = _random_day_in_range(rnd, window_start, window_end)
        t1 = datetime.combine(d, time(hour=hour, minute=minute, second=0))
        t2 = datetime.combine(d, time(hour=hour, minute=min(59, minute + 3), second=rnd.randint(0, 59)))
        rows = []
        for txn_dt in (t1, t2):
            row = _build_row(
                cols,
                rnd,
                user_id=user_id,
                txn_dt=txn_dt,
                amount=amt,
                merchant=merchant[:200],
                category=cat[:50],
                txn_type=typ,
                description=desc[:500] if desc else None,
            )
            if "is_fraud" in cols:
                row["is_fraud"] = True
            if "anomaly_flag" in cols:
                row["anomaly_flag"] = True
            rows.append(row)
        return rows

    dates: list[date]
    if _should_expand_monthly(t) and dom:
        series = _month_series(window_start, window_end, int(dom))
        dates = series[:max_monthly]
        if not dates:
            dates = [_random_day_in_range(rnd, window_start, window_end)]
    else:
        dates = [_random_day_in_range(rnd, window_start, window_end)]

    rows: list[dict[str, Any]] = []
    for d in dates:
        txn_dt = datetime.combine(d, time(hour=hour, minute=minute, second=rnd.randint(0, 59)))
        row = _build_row(
            cols,
            rnd,
            user_id=user_id,
            txn_dt=txn_dt,
            amount=amt,
            merchant=merchant[:200],
            category=cat[:50],
            txn_type=typ,
            description=desc[:500] if desc else None,
        )
        if t.get("is_fraud_pattern") and "is_fraud" in cols:
            row["is_fraud"] = True
        if t.get("is_fraud_pattern") and "anomaly_flag" in cols:
            row["anomaly_flag"] = True
        rows.append(row)
    return rows


def _fetch_persona_row(cur: Any, persona_key: str | None) -> dict[str, Any]:
    if persona_key:
        cur.execute(
            "SELECT * FROM user_personas WHERE lower(persona_key) = lower(%s) LIMIT 1;",
            (persona_key,),
        )
    else:
        cur.execute("SELECT * FROM user_personas ORDER BY random() LIMIT 1;")
    colnames = [d[0] for d in cur.description]
    r = cur.fetchone()
    if not r:
        raise RuntimeError("No personas in user_personas — run upsert_personas or apply migration.")
    return dict(zip(colnames, r))


def _fetch_templates(
    cur: Any,
    persona: dict[str, Any],
    limit: int,
    salt: str,
    relax_age: bool,
) -> list[dict[str, Any]]:
    inc = float(persona["monthly_income"] or 0)
    tier = int(persona["city_tier"] or 2)
    ag = str(persona.get("age_group") or "")
    q = """
        SELECT id, category, subcategory, merchant_name, amount, transaction_type, description,
               frequency, day_of_month, typical_hour, min_income, max_income, age_group, city_tier, lifestyle,
               is_emi, is_subscription, is_fraud_pattern, fraud_type, seasonal_tag
        FROM transaction_seed_data t
        WHERE (t.min_income IS NULL OR t.min_income <= %s)
          AND (t.max_income IS NULL OR t.max_income >= %s)
          AND (t.city_tier IS NULL OR t.city_tier = %s)
    """
    params: list[Any] = [inc, inc, tier]
    if not relax_age:
        q += " AND (t.age_group IS NULL OR t.age_group = %s)"
        params.append(ag)
    q += " ORDER BY md5(t.id::text || %s) LIMIT %s"
    params.extend([salt, limit])
    cur.execute(q, params)
    colnames = [d[0] for d in cur.description]
    return [dict(zip(colnames, row)) for row in cur.fetchall()]


def assign_corpus_to_user(
    cur: Any,
    user_id: int,
    *,
    count: int = 1200,
    persona_key: str | None = None,
    seed: int | None = None,
    max_monthly_expansions: int = 8,
) -> int:
    """
    Materialize ``count`` (approx) transactions from ``transaction_seed_data`` for ``user_id``.

    Monthly salary / EMI / subscription templates are expanded across the date window (capped).
    """
    upsert_personas(cur)
    cur.execute("SELECT COUNT(*) FROM transaction_seed_data;")
    pool = int(cur.fetchone()[0] or 0)
    if pool < 500:
        logger.warning(
            "transaction_seed_data has only %s rows — run generate_indian_fintech_corpus.py --db first",
            pool,
        )
        return 0

    rnd = random.Random((seed or user_id * 7919) % (2**32))
    persona = _fetch_persona_row(cur, persona_key)
    pid = int(persona["id"])

    cur.execute(
        """
        UPDATE users SET monthly_income = %s
        WHERE id = %s AND (monthly_income IS NULL OR monthly_income <= 0);
        """,
        (float(persona["monthly_income"] or 0), user_id),
    )

    months_back = rnd.randint(7, 12)
    window_end = date.today()
    window_start = window_end - timedelta(days=30 * months_back)

    want = max(500, min(2000, int(count)))
    salt = f"{user_id}:{persona['persona_key']}:{seed or 0}"
    templates = _fetch_templates(cur, persona, min(pool, max(2000, want * 2)), salt, relax_age=False)
    if len(templates) < want // 2:
        templates.extend(
            _fetch_templates(cur, persona, min(pool, want * 2), salt + ":relax", relax_age=True)
        )
    rnd.shuffle(templates)

    cols = _fetch_transaction_columns(cur)
    materialized: list[dict[str, Any]] = []
    for t in templates:
        materialized.extend(
            _template_to_txn_rows(
                t,
                user_id=user_id,
                cols=cols,
                rnd=rnd,
                window_start=window_start,
                window_end=window_end,
                max_monthly=max_monthly_expansions,
            )
        )
        if len(materialized) >= want * 3:
            break

    if len(materialized) > want:
        materialized = rnd.sample(materialized, want)

    inserted = bulk_insert_transaction_dicts(cur, materialized)
    cur.execute(
        """
        INSERT INTO user_transaction_assignments (user_id, persona_id, template_count, date_span_days, notes)
        VALUES (%s, %s, %s, %s, %s);
        """,
        (user_id, pid, len(templates), (window_end - window_start).days, "corpus_assign"),
    )
    return inserted
