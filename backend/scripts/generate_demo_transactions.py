#!/usr/bin/env python3
"""
Deterministic synthetic PostgreSQL transaction loader for SmartSpend hackathon demos.
Indian urban bank patterns, ~3 years of history, reproducible (random.seed(42)).
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "smartspend_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

DEMO_EMAIL_SUFFIX = "@demo.smartspend.local"
DEMO_EMAIL_LIKE = f"%{DEMO_EMAIL_SUFFIX}"

PAGE_SIZE = 1000


def _txn_features(txn_date: date, txn_time: time) -> tuple[int, int, bool, bool]:
    dt = datetime.combine(txn_date, txn_time)
    dow = int(dt.weekday())
    hour = int(txn_time.hour)
    is_weekend = dow >= 5
    is_night = hour >= 23 or hour < 5
    return hour, dow, is_weekend, is_night


@dataclass(frozen=True)
class Persona:
    email: str
    name: str
    monthly_income: int
    rent: int
    salary_day: int  # 1-28
    rent_day: int
    alloc_weight: float
    opening_income_mult_min: float
    opening_income_mult_max: float
    emi_chains: tuple[tuple[str, str, int, int], ...]  # merchant, category, base_amount, due_day 1-28


DEMO_PERSONAS: tuple[Persona, ...] = (
    Persona(
        "aanya_rich@demo.smartspend.local",
        "Aanya Mehta",
        350_000,
        95_000,
        28,
        2,
        0.35,
        4.5,
        6.0,
        (
            ("HDFC HOME LOAN EMI", "EMI", 42_000, 5),
            ("ICICI CAR LOAN EMI", "EMI", 18_500, 8),
            ("BAJAJ FINANCE PERSONAL LOAN", "EMI", 12_500, 12),
            ("APPLE INDIA EMI - IPHONE", "EMI", 2_299, 18),
        ),
    ),
    Persona(
        "rahul_upper@demo.smartspend.local",
        "Rahul Sharma",
        120_000,
        38_000,
        25,
        3,
        0.28,
        3.0,
        5.0,
        (
            ("HDFC HOME LOAN EMI", "EMI", 28_000, 5),
            ("ICICI CAR LOAN EMI", "EMI", 12_000, 10),
            ("BAJAJ FINANCE PERSONAL LOAN", "EMI", 8_500, 15),
        ),
    ),
    Persona(
        "priya_middle@demo.smartspend.local",
        "Priya Nair",
        65_000,
        22_000,
        1,
        4,
        0.20,
        2.5,
        4.5,
        (
            ("LIC HOUSING FINANCE EMI", "EMI", 15_000, 7),
            ("BAJAJ FINANCE PERSONAL LOAN", "EMI", 4_200, 12),
            ("SAMSUNG FINANCE EMI", "EMI", 1_899, 20),
        ),
    ),
    Persona(
        "vikram_stretched@demo.smartspend.local",
        "Vikram Patil",
        45_000,
        18_000,
        5,
        6,
        0.12,
        2.0,
        3.5,
        (
            ("BAJAJ FINANCE PERSONAL LOAN", "EMI", 5_500, 8),
            ("HDFC CREDIT CARD EMI", "EMI", 2_400, 22),
        ),
    ),
    Persona(
        "neha_student@demo.smartspend.local",
        "Neha Kulkarni",
        15_000,
        6_500,
        10,
        2,
        0.05,
        2.0,
        3.0,
        (("FLIPKART PAY LATER EMI", "EMI", 999, 14),),
    ),
)


def clamp_total(n: int) -> int:
    return max(20_000, min(30_000, n))


def clamp_min_per_user(n: int) -> int:
    if n < 80:
        logger.warning("--min-per-user %s is below hard floor 80; clamping to 80", n)
        return 80
    return n


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT to_regclass(%s) IS NOT NULL",
        (f"public.{table}",),
    )
    return bool(cur.fetchone()[0])


def upsert_demo_users(cur, personas: Sequence[Persona]) -> list[int]:
    ids: list[int] = []
    for p in personas:
        cur.execute(
            """
            INSERT INTO users (name, email, monthly_income)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET
                name = EXCLUDED.name,
                monthly_income = EXCLUDED.monthly_income,
                updated_at = NOW()
            RETURNING id
            """,
            (p.name, p.email, Decimal(p.monthly_income)),
        )
        row = cur.fetchone()
        ids.append(int(row[0]))
    return ids


def fetch_demo_user_ids(cur) -> list[int]:
    cur.execute(
        f"""
        SELECT id FROM users
        WHERE email LIKE %s
        ORDER BY id
        """,
        (DEMO_EMAIL_LIKE,),
    )
    return [int(r[0]) for r in cur.fetchall()]


def clear_demo_transactions(cur) -> int:
    """Remove demo users' transactions; only touches @demo.smartspend.local users."""
    cur.execute(
        f"""
        SELECT id FROM users WHERE email LIKE %s
        """,
        (DEMO_EMAIL_LIKE,),
    )
    demo_ids = [int(r[0]) for r in cur.fetchall()]
    if not demo_ids:
        logger.info("No demo users found; nothing to clear.")
        return 0

    if table_exists(cur, "fraud_alerts"):
        cur.execute(
            """
            DELETE FROM fraud_alerts
            WHERE transaction_id IN (
                SELECT id FROM transactions WHERE user_id = ANY(%s)
            )
            """,
            (demo_ids,),
        )
        logger.info("Deleted fraud_alerts rows referencing demo transactions (if any).")

    cur.execute(
        "DELETE FROM transactions WHERE user_id = ANY(%s)",
        (demo_ids,),
    )
    deleted = cur.rowcount
    logger.info("Deleted %s transactions for demo users.", deleted)
    return deleted


def month_iter(d0: date, d1: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, m = d0.year, d0.month
    while True:
        cur = date(y, m, 1)
        if cur > d1:
            break
        out.append((y, m))
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
    return out


def clamp_dom(y: int, mo: int, dom: int) -> int:
    _, last = monthrange(y, mo)
    return max(1, min(dom, last))


def sample_time(rng: random.Random, txn_date: date, category: str | None) -> time:
    r = rng.random()
    dow = txn_date.weekday()
    if category in ("Food", "Food Delivery") and dow < 5 and rng.random() < 0.18:
        hour = rng.randint(12, 13)
    elif category in ("Shopping", "Entertainment") and dow >= 5 and rng.random() < 0.22:
        hour = rng.randint(14, 20)
    elif dow < 5 and rng.random() < 0.12 and category not in ("Salary", "Rent", "EMI"):
        hour = rng.randint(18, 20)
    elif r < 0.70:
        hour = rng.randint(9, 20)
    elif r < 0.78:
        hour = rng.choice([23, 0, 1, 2, 3, 4])
    else:
        hour = rng.randint(0, 23)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return time(hour, minute, second)


def diwali_windows(rng: random.Random, years: Sequence[int]) -> set[date]:
    """Seven consecutive days in Oct–Nov per calendar year; amounts multiplier applied elsewhere."""
    s: set[date] = set()
    for y in years:
        start_oct = date(y, 10, 15)
        end_nov = date(y, 11, 15)
        span = (end_nov - start_oct).days
        off = rng.randint(0, max(0, span - 6))
        d0 = start_oct + timedelta(days=off)
        for k in range(7):
            s.add(d0 + timedelta(days=k))
    return s


def discretionary_mult(d: date, diwali_days: set[date]) -> Decimal:
    return Decimal("1.4") if d in diwali_days else Decimal("1")


def food_delivery_amount(rng: random.Random, mult: Decimal) -> Decimal:
    if rng.random() < 0.65:
        base = rng.uniform(250, 400)
    else:
        base = rng.uniform(180, 520)
    return (Decimal(str(round(base, 2))) * mult).quantize(Decimal("0.01"))


def grocery_amount(rng: random.Random, mult: Decimal, big_shop: bool) -> Decimal:
    if big_shop:
        base = rng.uniform(3000, 12000)
    else:
        base = rng.uniform(800, 4500)
    return (Decimal(str(round(base, 2))) * mult).quantize(Decimal("0.01"))


def fuel_amount(rng: random.Random, mult: Decimal) -> Decimal:
    base = rng.uniform(500, 2200)
    return (Decimal(str(round(base, 2))) * mult).quantize(Decimal("0.01"))


def micro_upi_amount(rng: random.Random) -> Decimal:
    return Decimal(str(rng.randint(20, 199)))


def jitter_pct(rng: random.Random, low: float, high: float) -> Decimal:
    p = rng.uniform(low, high) / 100.0
    return Decimal(str(round(1 + p, 6)))


def pick_merchant_food(rng: random.Random) -> str:
    return rng.choice(
        ["SWIGGY", "SWIGGY INSTAMART", "ZOMATO", "ZOMATO LIMITED", "ZOMATO ORDER"]
    )


def pick_merchant_grocery(rng: random.Random) -> str:
    return rng.choice(
        [
            "BIGBASKET",
            "DMART READY",
            "RELIANCE SMART",
            "BLINKIT",
            "JIO MART",
            "MORE RETAIL",
        ]
    )


def pick_merchant_travel(rng: random.Random) -> str:
    return rng.choice(["UBER INDIA", "OLA", "IRCTC", "RAPIDO"])


def pick_merchant_shopping(rng: random.Random) -> str:
    return rng.choice(
        ["AMAZON PAY", "AMAZON.IN", "FLIPKART", "MYNTRA", "AJIO", "NYKAA"]
    )


def pick_merchant_bills(rng: random.Random) -> str:
    return rng.choice(
        [
            "JIO POSTPAID",
            "AIRTEL",
            "VI RECHARGE",
            "BESCOM BILLDESK",
            "BWSSB",
            "LIC PREMIUM",
        ]
    )


def pick_location(rng: random.Random) -> str:
    return rng.choice(
        ["Mumbai, MH", "Bengaluru, KA", "Pune, MH", "Hyderabad, TS", "Chennai, TN"]
    )


def pick_payment(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.62:
        return "UPI"
    if r < 0.82:
        return "Card"
    if r < 0.96:
        return "NetBanking"
    return "IMPS"


def maybe_description(rng: random.Random) -> str | None:
    if rng.random() < 0.35:
        return None
    return rng.choice(
        [
            f"UPI/{rng.randint(100000, 999999)}/paytm.{rng.randint(1000, 9999)}",
            f"UPI-{rng.randint(1000000000, 9999999999)}",
            f"NEFT-{rng.randint(100000, 999999)}-HDFC",
            None,
        ]
    )


def spaced_month_indices(n_months: int, n_pay: int, salt: int) -> list[int]:
    """Spread EMI payments across the timeline (deterministic positions)."""
    if n_months <= 0 or n_pay <= 0:
        return []
    n_pay = min(n_pay, n_months)
    if n_pay == n_months:
        return list(range(n_months))
    phase = salt % max(1, n_months // max(n_pay, 1))
    out: list[int] = []
    for j in range(n_pay):
        pos = min(
            n_months - 1,
            phase + int(j * (n_months - 1) / max(n_pay - 1, 1)),
        )
        out.append(pos)
    seen: set[int] = set()
    uniq: list[int] = []
    for p in sorted(out):
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    x = 0
    while len(uniq) < n_pay and x < n_months:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
        x += 1
    return sorted(uniq)[:n_pay]


def _row(
    user_id: int,
    d: date,
    tt: time,
    amount: Decimal,
    typ: str,
    description: str | None,
    merchant: str,
    category: str,
    subcategory: str | None,
    payment_method: str,
    location: str,
    reference_number: str | None,
    desc_override: str | None,
    anomaly_flag: bool,
    risk_score: int,
    risk_level: str,
    anomaly_reason: str | None,
    ml_processed: bool,
    sort_bucket: str,
) -> dict[str, Any]:
    desc = desc_override if desc_override is not None else description
    hod, dow, is_we, is_ni = _txn_features(d, tt)
    return {
        "user_id": user_id,
        "transaction_date": d,
        "transaction_time": tt,
        "amount": amount,
        "type": typ,
        "description": desc,
        "merchant": merchant,
        "category": category,
        "subcategory": subcategory,
        "payment_method": payment_method,
        "location": location,
        "balance_after": None,
        "reference_number": reference_number,
        "hour_of_day": hod,
        "day_of_week": dow,
        "is_weekend": is_we,
        "is_night_txn": is_ni,
        "anomaly_flag": anomaly_flag,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "anomaly_reason": anomaly_reason,
        "ml_processed": ml_processed,
        "_sort_bucket": sort_bucket,
        "_dow": dow,
    }


def complete_skeleton(
    rng: random.Random,
    user_id: int,
    persona: Persona,
    months: list[tuple[int, int]],
    diwali_days: set[date],
    M: int,
) -> list[dict[str, Any]]:
    """Exactly M rows: monthly salary+rent, spaced EMIs, then discretionary fill."""
    rows: list[dict[str, Any]] = []
    income = Decimal(persona.monthly_income)
    rent_amt = Decimal(persona.rent)
    stretch_end_small = persona.monthly_income <= 50_000
    nm = len(months)
    base = 2 * nm
    if base > M:
        raise ValueError(
            f"min-per-user {M} too small for {nm} calendar months of salary+rent (need >= {base})."
        )

    left = M - base
    chains = list(persona.emi_chains)
    if chains:
        emi_budget = int(left * 0.42)
        emi_budget = min(emi_budget, len(chains) * 36, left)
        emi_budget = max(emi_budget, min(len(chains) * 2, left // 2))
        emi_budget = min(emi_budget, left)
        tail_len = min(6, nm)
        emi_runway = len(chains) * tail_len
        emi_budget = max(emi_budget, min(emi_runway, left))
        if persona.email.startswith("neha_"):
            emi_budget = min(emi_budget, 12)
        emi_budget = max(0, min(emi_budget, left))
    else:
        emi_budget = 0

    for y, m in months:
        sd = clamp_dom(y, m, persona.salary_day)
        sal_date = date(y, m, sd)
        amt = (income * jitter_pct(rng, 0, 2)).quantize(Decimal("0.01"))
        tt = time(9, rng.randint(0, 45), 0)
        rows.append(
            _row(
                user_id,
                sal_date,
                tt,
                amt,
                "CREDIT",
                "SALARY CREDIT",
                persona.email.split("@")[0].upper() + " PAYROLL",
                "Salary",
                "Payroll",
                "NEFT",
                pick_location(rng),
                f"SAL-{y}{m:02d}-{rng.randint(1000, 9999)}",
                None,
                False,
                0,
                "LOW",
                None,
                False,
                "a",
            )
        )

        rd = date(y, m, clamp_dom(y, m, persona.rent_day + rng.choice([-1, 0, 1])))
        rtime = time(10, rng.randint(0, 50), rng.randint(0, 59))
        rows.append(
            _row(
                user_id,
                rd,
                rtime,
                rent_amt,
                "DEBIT",
                None,
                "RENT TRANSFER LANDLORD",
                "Rent",
                "Housing",
                "UPI",
                pick_location(rng),
                None,
                None,
                False,
                0,
                "LOW",
                None,
                False,
                "b",
            )
        )

    if chains and emi_budget > 0:
        tail = months[-6:] if nm >= 6 else list(months)
        runway_count = 0
        for y, m in tail:
            for merch, cat, base_amt, due in chains:
                if runway_count >= emi_budget:
                    break
                due_d = date(y, m, clamp_dom(y, m, due + rng.choice([-1, 0, 1])))
                emi_amt = (Decimal(base_amt) * jitter_pct(rng, -2, 2)).quantize(Decimal("0.01"))
                et = time(14, rng.randint(0, 59), rng.randint(0, 59))
                rows.append(
                    _row(
                        user_id,
                        due_d,
                        et,
                        emi_amt,
                        "DEBIT",
                        None,
                        merch,
                        cat,
                        "Loan",
                        "NetBanking",
                        pick_location(rng),
                        f"ACH-{rng.randint(100000, 999999)}",
                        None,
                        False,
                        0,
                        "LOW",
                        None,
                        False,
                        "c",
                    )
                )
                runway_count += 1
            if runway_count >= emi_budget:
                break

        spaced_budget = emi_budget - runway_count
        tail_set = set(tail)
        if spaced_budget > 0:
            per_chain = [spaced_budget // len(chains)] * len(chains)
            for j in range(spaced_budget % len(chains)):
                per_chain[j] += 1
            for ci, (merch, cat, base_amt, due) in enumerate(chains):
                cnt = per_chain[ci]
                if cnt <= 0:
                    continue
                non_tail = [i for i in range(nm) if months[i] not in tail_set]
                if not non_tail:
                    continue
                for mi in spaced_month_indices(len(non_tail), cnt, ci + 17 * (1 + sum(ord(c) for c in merch) % 1000)):
                    idx = non_tail[mi]
                    y, m = months[idx]
                    due_d = date(y, m, clamp_dom(y, m, due + rng.choice([-1, 0, 1])))
                    emi_amt = (Decimal(base_amt) * jitter_pct(rng, -2, 2)).quantize(Decimal("0.01"))
                    et = time(14, rng.randint(0, 59), rng.randint(0, 59))
                    rows.append(
                        _row(
                            user_id,
                            due_d,
                            et,
                            emi_amt,
                            "DEBIT",
                            None,
                            merch,
                            cat,
                            "Loan",
                            "NetBanking",
                            pick_location(rng),
                            f"ACH-{rng.randint(100000, 999999)}",
                            None,
                            False,
                            0,
                            "LOW",
                            None,
                            False,
                            "c",
                        )
                    )

    is_neha = persona.email.startswith("neha_")
    while len(rows) < M:
        y, m = rng.choice(months)
        last_dom = monthrange(y, m)[1]
        dom = rng.randint(1, last_dom)
        d = date(y, m, dom)
        mult = discretionary_mult(d, diwali_days)
        if stretch_end_small and dom >= last_dom - 4 and rng.random() < 0.35:
            mult = mult * Decimal("0.85")

        if is_neha and rng.random() < 0.14:
            rows.append(
                _row(
                    user_id,
                    d,
                    time(11, rng.randint(0, 59), 0),
                    Decimal("649.00"),
                    "DEBIT",
                    maybe_description(rng),
                    "NETFLIX INDIA",
                    "Entertainment",
                    "Subscription",
                    "UPI",
                    pick_location(rng),
                    None,
                    None,
                    False,
                    0,
                    "LOW",
                    None,
                    False,
                    "d",
                )
            )
            continue

        kind = rng.choices(
            ["micro", "food", "fuel", "grocery", "shop", "bill", "travel"],
            weights=[0.28, 0.18, 0.10, 0.14, 0.12, 0.10, 0.08],
            k=1,
        )[0]

        if kind == "micro":
            cat = "Misc"
            merch = rng.choice(["TEA STALL UPI", "AUTO RICKSHAW", "STALL PAY", "CANTEEN"])
            amt = micro_upi_amount(rng)
            sub = "UPI Micro"
        elif kind == "food":
            cat = "Food Delivery"
            merch = pick_merchant_food(rng)
            amt = food_delivery_amount(rng, mult)
            sub = "Delivery"
        elif kind == "fuel":
            cat = "Fuel"
            merch = rng.choice(["SHELL INDIA", "HPCL", "IOCL", "BPCL"])
            amt = fuel_amount(rng, mult)
            sub = "Petrol"
        elif kind == "grocery":
            cat = "Groceries"
            merch = pick_merchant_grocery(rng)
            amt = grocery_amount(rng, mult, rng.random() < 0.12)
            sub = "Retail"
        elif kind == "shop":
            cat = "Shopping"
            merch = pick_merchant_shopping(rng)
            base = rng.uniform(400, 9000)
            amt = (Decimal(str(round(base, 2))) * mult).quantize(Decimal("0.01"))
            sub = "Online"
        elif kind == "bill":
            cat = "Bills"
            merch = pick_merchant_bills(rng)
            amt = Decimal(str(rng.choice([299, 399, 499, 799, 899, 1299])))
            sub = "Utilities"
        else:
            cat = "Travel"
            merch = pick_merchant_travel(rng)
            base = rng.uniform(120, 1800)
            amt = (Decimal(str(round(base, 2))) * mult).quantize(Decimal("0.01"))
            sub = "Local"

        tt = sample_time(rng, d, cat)
        rows.append(
            _row(
                user_id,
                d,
                tt,
                amt,
                "DEBIT",
                maybe_description(rng),
                merch,
                cat,
                sub,
                pick_payment(rng),
                pick_location(rng),
                None,
                None,
                False,
                0,
                "LOW",
                None,
                False,
                "z",
            )
        )

    if len(rows) != M:
        raise RuntimeError(f"skeleton row count {len(rows)} != M {M}")
    return rows


def extra_fill_rows(
    rng: random.Random,
    user_id: int,
    persona: Persona,
    d0: date,
    d1: date,
    diwali_days: set[date],
    count: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stretch = persona.monthly_income <= 50_000
    n_refund = min(max(0, count // 800), count)
    n_main = count - n_refund
    for idx in range(count):
        span = (d1 - d0).days + 1
        d = d0 + timedelta(days=rng.randint(0, max(0, span - 1)))
        if idx >= n_main:
            tt = sample_time(rng, d, "Misc")
            rows.append(
                _row(
                    user_id,
                    d,
                    tt,
                    Decimal(str(rng.choice([49, 99, 149, 199, 299]))),
                    "CREDIT",
                    "REFUND CREDIT",
                    rng.choice(["AMAZON PAY", "FLIPKART", "SWIGGY"]),
                    "Refund",
                    "Reversal",
                    "UPI",
                    pick_location(rng),
                    None,
                    None,
                    False,
                    0,
                    "LOW",
                    None,
                    False,
                    "r",
                )
            )
            continue

        mult = discretionary_mult(d, diwali_days)
        if stretch and d.day >= 25:
            mult = mult * Decimal("0.88")

        kind = rng.choices(
            ["micro", "food", "fuel", "grocery", "shop", "bill", "travel", "health"],
            weights=[0.30, 0.16, 0.10, 0.14, 0.12, 0.10, 0.06, 0.02],
            k=1,
        )[0]

        if kind == "micro":
            cat = "Misc"
            merch = rng.choice(["TEA STALL UPI", "AUTO RICKSHAW", "PAANI PURI", "XEROX"])
            amt = micro_upi_amount(rng)
            sub = "UPI Micro"
        elif kind == "food":
            cat = "Food Delivery"
            merch = pick_merchant_food(rng)
            amt = food_delivery_amount(rng, mult)
            sub = "Delivery"
        elif kind == "fuel":
            cat = "Fuel"
            merch = rng.choice(["SHELL INDIA", "HPCL", "IOCL"])
            amt = fuel_amount(rng, mult)
            sub = "Petrol"
        elif kind == "grocery":
            cat = "Groceries"
            merch = pick_merchant_grocery(rng)
            amt = grocery_amount(rng, mult, rng.random() < 0.15)
            sub = "Retail"
        elif kind == "shop":
            cat = "Shopping"
            merch = pick_merchant_shopping(rng)
            base = rng.uniform(350, 12000)
            amt = (Decimal(str(round(base, 2))) * mult).quantize(Decimal("0.01"))
            sub = "Online"
        elif kind == "bill":
            cat = "Bills"
            merch = pick_merchant_bills(rng)
            amt = Decimal(str(rng.choice([199, 299, 499, 699, 999])))
            sub = "Utilities"
        elif kind == "health":
            cat = "Healthcare"
            merch = rng.choice(["APOLLO PHARMACY", "MAX HEALTHCARE", "LAL PATHLABS"])
            amt = Decimal(str(round(rng.uniform(350, 2200), 2)))
            sub = "Medical"
        else:
            cat = "Travel"
            merch = pick_merchant_travel(rng)
            base = rng.uniform(90, 2200)
            amt = (Decimal(str(round(base, 2))) * mult).quantize(Decimal("0.01"))
            sub = "Local"

        tt = sample_time(rng, d, cat)
        rows.append(
            _row(
                user_id,
                d,
                tt,
                amt,
                "DEBIT",
                maybe_description(rng),
                merch,
                cat,
                sub,
                pick_payment(rng),
                pick_location(rng),
                None,
                None,
                False,
                0,
                "LOW",
                None,
                False,
                "x",
            )
        )
    return rows


def sort_key(r: dict[str, Any]) -> tuple:
    cr = 0 if r["type"] == "CREDIT" else 1
    return (
        r["transaction_date"],
        r["transaction_time"],
        cr,
        r.get("_sort_bucket", ""),
        r["merchant"],
    )


def apply_running_balance(
    rows_by_user: dict[int, list[dict[str, Any]]],
    personas_by_uid: dict[int, Persona],
    rng: random.Random,
) -> None:
    floor_bal = Decimal("500")
    for uid, lst in rows_by_user.items():
        p = personas_by_uid[uid]
        opening = Decimal(
            str(round(rng.uniform(p.opening_income_mult_min, p.opening_income_mult_max) * p.monthly_income, 2))
        )
        sorted_rows = sorted(lst, key=sort_key)
        bal = opening
        for r in sorted_rows:
            amt = r["amount"]
            if r["type"] == "CREDIT":
                bal += amt
            else:
                nb = bal - amt
                if p.monthly_income >= 55_000 and nb < floor_bal:
                    nb = floor_bal
                elif nb < floor_bal:
                    nb = floor_bal
                bal = nb
            r["balance_after"] = bal


def inject_anomaly_patterns(
    rng: random.Random,
    rows_by_user: dict[int, list[dict[str, Any]]],
    personas_by_uid: dict[int, Persona],
    add_probe_pair: bool,
) -> None:
    """Flag ~3–5% of debits with diverse reasons; add ₹5 + large same-day pair for one heavy user."""
    reasons_cycle = [
        ("ODD_HOUR_LARGE", "HIGH", 78, "Large debit at unusual hour"),
        ("DUPLICATE_SPIKE", "HIGH", 85, "Repeated merchant debits same day"),
        ("CATEGORY_BREAKOUT", "MEDIUM", 55, "Unusual category vs baseline"),
        ("FOREIGN_MERCHANT", "MEDIUM", 58, "International-style merchant pattern"),
        ("POST_SALARY_SPIKE", "HIGH", 88, "Spike right after salary credit"),
        ("DIWALI_BURST", "MEDIUM", 52, "Festive discretionary burst"),
        ("DORMANT_WAKE", "MEDIUM", 60, "Spend after quiet period"),
        ("CC_MIN_PATTERN", "MEDIUM", 57, "Minimum due style small card payment"),
        ("HEALTH_EMERGENCY", "CRITICAL", 92, "Large healthcare debit"),
        ("UPI_PROBE_SAME_DAY", "MEDIUM", 62, "Micro UPI probe same day as large spend"),
    ]

    for uid, lst in rows_by_user.items():
        debits = [r for r in lst if r["type"] == "DEBIT"]
        n = len(debits)
        if n == 0:
            continue
        k = max(1, min(int(n * 0.045), int(n * 0.055), int(n * 0.06)))
        idxs = list(range(n))
        rng.shuffle(idxs)
        pick = set(idxs[:k])

        for i, r in enumerate(debits):
            if i not in pick:
                continue
            code, lvl, score, msg = reasons_cycle[i % len(reasons_cycle)]
            r["anomaly_flag"] = True
            r["risk_score"] = min(95, max(45, score + rng.randint(-4, 4)))
            r["risk_level"] = lvl
            r["anomaly_reason"] = msg
            if code == "ODD_HOUR_LARGE":
                r["transaction_time"] = time(rng.choice([0, 1, 2, 3, 23]), rng.randint(0, 59), 0)
                r["amount"] = max(r["amount"], Decimal(str(rng.randint(15000, 85000))))
            elif code == "DUPLICATE_SPIKE":
                r["merchant"] = "SWIGGY"
                r["category"] = "Food Delivery"
                r["amount"] = (r["amount"] * Decimal("1.05")).quantize(Decimal("0.01"))
            elif code == "CATEGORY_BREAKOUT":
                r["category"] = "Shopping"
                r["merchant"] = "BOOKMYSHOW"
                r["subcategory"] = "Tickets"
            elif code == "FOREIGN_MERCHANT":
                r["merchant"] = "CURSOR US CHARGE"
                r["amount"] = Decimal(str(round(rng.uniform(3, 49), 2)))
            elif code == "POST_SALARY_SPIKE":
                r["amount"] = max(r["amount"], Decimal(str(rng.randint(12000, 45000))))
                r["merchant"] = "CROMA RETAIL"
            elif code == "DIWALI_BURST":
                r["amount"] = (r["amount"] * Decimal("1.35")).quantize(Decimal("0.01"))
                r["merchant"] = "NYKAA"
            elif code == "DORMANT_WAKE":
                r["amount"] = max(r["amount"], Decimal("4500"))
            elif code == "CC_MIN_PATTERN":
                r["amount"] = Decimal(str(rng.choice([500, 750, 1100])))
                r["merchant"] = "HDFC CC MINIMUM DUE"
                r["payment_method"] = "Card"
            elif code == "HEALTH_EMERGENCY":
                r["category"] = "Healthcare"
                r["merchant"] = "MAX HEALTHCARE"
                r["amount"] = Decimal(str(rng.randint(25000, 95000)))

            hod, dow, is_we, is_ni = _txn_features(r["transaction_date"], r["transaction_time"])
            r["hour_of_day"] = hod
            r["day_of_week"] = dow
            r["is_weekend"] = is_we
            r["is_night_txn"] = is_ni

    if not add_probe_pair:
        return

    for uid, lst in rows_by_user.items():
        if personas_by_uid[uid].monthly_income < 100_000:
            continue
        deb = [r for r in lst if r["type"] == "DEBIT"]
        if len(deb) < 5:
            continue
        r0 = rng.choice(deb)
        d0 = r0["transaction_date"]
        probe = _row(
            uid,
            d0,
            time(10, 12, 0),
            Decimal("5"),
            "DEBIT",
            "UPI/000001/probe",
            "UPI MICRO",
            "Misc",
            "Probe",
            "UPI",
            pick_location(rng),
            None,
            None,
            True,
            55,
            "MEDIUM",
            "₹5 UPI probe",
            False,
            "p",
        )
        big = _row(
            uid,
            d0,
            time(18, 44, 0),
            Decimal(str(rng.randint(40000, 120000))),
            "DEBIT",
            None,
            "LUXURY MALL POS",
            "Shopping",
            "POS",
            "Card",
            pick_location(rng),
            None,
            None,
            True,
            90,
            "HIGH",
            "Large debit same day as micro probe",
            False,
            "q",
        )
        lst.extend([probe, big])
        break


def recompute_time_features(rows: list[dict[str, Any]]) -> None:
    for r in rows:
        hod, dow, is_we, is_ni = _txn_features(r["transaction_date"], r["transaction_time"])
        r["hour_of_day"] = hod
        r["day_of_week"] = dow
        r["is_weekend"] = is_we
        r["is_night_txn"] = is_ni


def strip_internal_keys(rows: list[dict[str, Any]]) -> list[tuple]:
    out = []
    for r in rows:
        r.pop("_sort_bucket", None)
        r.pop("_dow", None)
        out.append(
            (
                r["user_id"],
                r["transaction_date"],
                r["transaction_time"],
                r["amount"],
                r["type"],
                r["description"],
                r["merchant"],
                r["category"],
                r["subcategory"],
                r["payment_method"],
                r["location"],
                r["balance_after"],
                r["reference_number"],
                r["hour_of_day"],
                r["day_of_week"],
                r["is_weekend"],
                r["is_night_txn"],
                r["anomaly_flag"],
                r["risk_score"],
                r["risk_level"],
                r["anomaly_reason"],
                r["ml_processed"],
            )
        )
    return out


def bulk_insert(cur, rows: list[tuple], include_bank_name: bool) -> None:
    if include_bank_name:
        sql = """
            INSERT INTO transactions (
                user_id, transaction_date, transaction_time, amount, type,
                description, merchant, category, subcategory, payment_method,
                location, balance_after, reference_number,
                hour_of_day, day_of_week, is_weekend, is_night_txn,
                anomaly_flag, risk_score, risk_level, anomaly_reason, ml_processed,
                bank_name
            ) VALUES %s
        """
        template = "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        extended = [tuple(list(t) + ["SYNTH_DEMO"]) for t in rows]
        execute_values(cur, sql, extended, template=template, page_size=PAGE_SIZE)
    else:
        sql = """
            INSERT INTO transactions (
                user_id, transaction_date, transaction_time, amount, type,
                description, merchant, category, subcategory, payment_method,
                location, balance_after, reference_number,
                hour_of_day, day_of_week, is_weekend, is_night_txn,
                anomaly_flag, risk_score, risk_level, anomaly_reason, ml_processed
            ) VALUES %s
        """
        template = "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        execute_values(cur, sql, rows, template=template, page_size=PAGE_SIZE)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate deterministic demo transactions for SmartSpend.")
    p.add_argument("--total", type=int, default=25_000, help="Total transactions (clamped 20000–30000).")
    p.add_argument("--min-per-user", type=int, default=100, help="Minimum rows per demo user (>=80).")
    p.add_argument("--users", type=int, default=5, help="Number of demo personas (max 5 supported).")
    p.add_argument("--clear-demo", action="store_true", help="Delete demo users' transactions first.")
    p.add_argument("--dry-run", action="store_true", help="Print counts/sample only; no DB writes.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rng = random.Random(42)

    U = max(1, min(args.users, len(DEMO_PERSONAS)))
    personas = DEMO_PERSONAS[:U]

    T = clamp_total(args.total)
    if args.total != T:
        logger.info("Clamped --total from %s to band [20000,30000] → %s", args.total, T)

    M = clamp_min_per_user(args.min_per_user)
    if args.min_per_user < 80:
        pass

    if T < U * M:
        logger.error(
            "Need at least U * M transactions: %s users × %s min = %s, but total is %s. "
            "Increase --total or decrease --users / --min-per-user.",
            U,
            M,
            U * M,
            T,
        )
        return 2

    d_end = date.today()
    d_start = d_end - timedelta(days=365 * 3)
    months = month_iter(d_start, d_end)
    nm = len(months)
    if M < 2 * nm:
        logger.error(
            "--min-per-user %s must be >= %s (salary + rent for each of %s calendar months in the ~3y window).",
            M,
            2 * nm,
            nm,
        )
        return 2

    years = sorted({y for y, _ in months})
    diwali_days = diwali_windows(rng, years)

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        has_bank = column_exists(cur, "transactions", "bank_name")

        if args.dry_run:
            logger.info("DRY RUN: no database writes.")
            logger.info("Would use %s demo users, total=%s, min_per_user=%s, bank_name=%s", U, T, M, has_bank)
            sample = complete_skeleton(rng, 1, personas[0], months, diwali_days, M)
            logger.info("Sample skeleton size for user1: %s", len(sample))
            return 0

        if args.clear_demo:
            clear_demo_transactions(cur)
            conn.commit()

        demo_ids = upsert_demo_users(cur, personas)
        conn.commit()
        uid_by_email = {personas[i].email: demo_ids[i] for i in range(len(personas))}
        logger.info("Demo user ids: %s", uid_by_email)

        personas_by_uid = {demo_ids[i]: personas[i] for i in range(len(personas))}

        remaining = T - U * M
        weights = [p.alloc_weight for p in personas]
        sw = sum(weights)
        extra_counts = [int(remaining * w / sw) for w in weights]
        for i in range(remaining - sum(extra_counts)):
            extra_counts[i % U] += 1

        add_probe_pair = remaining >= 2 and any(p.monthly_income >= 100_000 for p in personas)
        if add_probe_pair:
            hi = next(i for i, p in enumerate(personas) if p.monthly_income >= 100_000)
            rem = 2
            for j in range(U):
                ii = (hi + j) % U
                take = min(rem, extra_counts[ii])
                extra_counts[ii] -= take
                rem -= take
                if rem <= 0:
                    break

        rows_by_user: dict[int, list[dict[str, Any]]] = {uid: [] for uid in demo_ids}

        for i, uid in enumerate(demo_ids):
            p = personas[i]
            skel = complete_skeleton(rng, uid, p, months, diwali_days, M)
            rows_by_user[uid].extend(skel)
            rows_by_user[uid].extend(
                extra_fill_rows(rng, uid, p, d_start, d_end, diwali_days, extra_counts[i])
            )

        inject_anomaly_patterns(rng, rows_by_user, personas_by_uid, add_probe_pair)

        all_rows: list[dict[str, Any]] = []
        for uid in demo_ids:
            all_rows.extend(rows_by_user[uid])

        by_u: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for r in all_rows:
            by_u[r["user_id"]].append(r)

        apply_running_balance(by_u, personas_by_uid, rng)

        flat: list[dict[str, Any]] = []
        for uid in demo_ids:
            flat.extend(by_u[uid])

        for r in flat:
            if not r["anomaly_flag"]:
                r["risk_level"] = "LOW"
                r["risk_score"] = rng.randint(0, 15) if r["type"] == "DEBIT" else rng.randint(0, 5)
                r["anomaly_reason"] = None

        recompute_time_features(flat)

        if len(flat) != T:
            logger.error("Internal error: built %s rows, expected %s", len(flat), T)
            return 1

        tuples = strip_internal_keys(flat)
        bulk_insert(cur, tuples, has_bank)
        conn.commit()

        cur.execute("ANALYZE transactions;")
        conn.commit()

        cur.execute(
            """
            SELECT user_id, COUNT(*) AS c
            FROM transactions
            WHERE user_id = ANY(%s)
            GROUP BY user_id
            ORDER BY user_id
            """,
            (demo_ids,),
        )
        counts = cur.fetchall()
        logger.info("Per-user transaction counts:")
        min_c = None
        for uid, c in counts:
            logger.info("  user_id=%s count=%s", uid, c)
            min_c = c if min_c is None else min(min_c, c)

        cur.execute(
            """
            SELECT COUNT(*) FROM transactions t
            JOIN users u ON u.id = t.user_id
            WHERE u.email LIKE %s AND t.anomaly_flag = TRUE AND t.type = 'DEBIT'
            """,
            (DEMO_EMAIL_LIKE,),
        )
        ano = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT COUNT(*) FROM transactions t
            JOIN users u ON u.id = t.user_id
            WHERE u.email LIKE %s AND t.type = 'DEBIT'
            """,
            (DEMO_EMAIL_LIKE,),
        )
        deb = int(cur.fetchone()[0])
        if deb:
            logger.info("Anomaly debits: %s / %s debits (%.2f%%)", ano, deb, 100.0 * ano / deb)

        cur.execute(
            """
            SELECT user_id FROM transactions
            WHERE user_id = ANY(%s)
            GROUP BY user_id
            HAVING COUNT(*) < %s
            """,
            (demo_ids, M),
        )
        bad = cur.fetchall()
        if bad:
            logger.error("Users below floor %s: %s", M, bad)
            return 1
        if min_c is not None and min_c < M:
            logger.error("Minimum count %s < required %s", min_c, M)
            return 1

        cur.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = ANY(%s)",
            (demo_ids,),
        )
        tot = int(cur.fetchone()[0])
        if tot != T:
            logger.error("Total demo transactions %s != expected %s", tot, T)
            return 1
        logger.info("Total demo transactions inserted: %s", tot)

        logger.info("Done. All demo users have >= %s transactions.", M)
        return 0
    except Exception:
        conn.rollback()
        logger.exception("Failed")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
