"""Generate 25k+ realistic Indian fintech-style rows for ``transaction_seed_data``."""

from __future__ import annotations

import random
from datetime import date
from decimal import Decimal
from typing import Any

# Default corpus size (tweak with ``total`` argument).
_DEFAULT_TOTAL = 26_000
_COUNTS: dict[str, int] = {
    "income": 1300,
    "emi": 2600,
    "subscription": 1500,
    "food": 4800,
    "transport": 2900,
    "shopping": 3800,
    "utility": 2000,
    "entertainment": 1900,
    "health": 1400,
    "festival": 2000,
    "fraud": 500,
    "misc": 1300,
}

_BRACKET_ENTRY = (25_000, 40_000)
_BRACKET_MID = (40_000, 80_000)
_BRACKET_SENIOR = (80_000, 150_000)
_BRACKET_EXEC = (150_000, 300_000)

_COMPANIES = (
    "TCS", "Infosys", "Wipro", "Accenture", "Amazon India", "Flipkart", "Zomato",
    "HDFC Bank", "ICICI Bank", "Axis Bank", "Deloitte", "EY India", "HCL Tech",
    "Mindtree", "Cognizant", "Capgemini", "Swiggy", "Meesho", "Razorpay",
)

_EMI_HOME = ("HDFC HOME LOAN EMI", "SBI HOME LOAN", "ICICI HOME FINANCE", "LIC HOUSING FINANCE EMI", "AXIS HOME LOAN")
_EMI_CAR = ("HDFC CAR LOAN EMI", "ICICI AUTO LOAN", "SBI AUTO FINANCE", "BAJAJ AUTO FINANCE")
_EMI_BIKE = ("BAJAJ FINSERV TWO WHEELER", "HERO FINCORP EMI", "HDFC BIKE LOAN")
_EMI_PL = ("MONEYTAP EMI", "KREDITBEE EMI", "PAYSENSE EMI", "LAZYPAY EMI", "NAVI PERSONAL LOAN")

_SUBS = (
    ("Netflix India", 649, "Entertainment"),
    ("Spotify India", 149, "Entertainment"),
    ("Amazon Prime Video", 179, "Entertainment"),
    ("Disney Hotstar", 299, "Entertainment"),
    ("Zee5 Subscription", 99, "Entertainment"),
    ("YouTube Premium India", 129, "Entertainment"),
    ("Apple Music India", 99, "Entertainment"),
    ("Kindle Unlimited", 149, "Entertainment"),
    ("Cult.fit Membership", 999, "Health"),
    ("Times Prime", 999, "Shopping"),
    ("Sony LIV", 299, "Entertainment"),
    ("Gaana Plus", 99, "Entertainment"),
)

_FOOD = (
    ("Swiggy", "Food", 220, 850),
    ("Zomato", "Food", 250, 920),
    ("Zepto", "Groceries", 320, 1600),
    ("Blinkit", "Groceries", 280, 1400),
    ("BigBasket", "Groceries", 1500, 4200),
    ("Dunzo Daily", "Groceries", 400, 1200),
    ("Thali House Indiranagar", "Food", 180, 450),
    ("Chai Point", "Food", 45, 220),
    ("Starbucks India", "Food", 250, 650),
)

_TRANSPORT = (
    ("Uber India", "Transport", 120, 780),
    ("Ola Cabs", "Transport", 110, 720),
    ("Rapido", "Transport", 35, 160),
    ("Shell Petrol Pump", "Transport", 500, 2200),
    ("HPCL Fuel", "Transport", 400, 1900),
    ("Metro Recharge DMRC", "Transport", 200, 600),
)

_SHOPPING = (
    ("Amazon India", "Shopping", 500, 18_000),
    ("Flipkart", "Shopping", 600, 14_000),
    ("Myntra", "Shopping", 900, 6500),
    ("Ajio", "Shopping", 800, 5500),
    ("Nykaa", "Shopping", 400, 4200),
    ("Croma Retail", "Shopping", 1200, 45_000),
    ("Reliance Digital", "Shopping", 800, 35_000),
)

_UTILITY = (
    ("BESCOM Electricity", "Utilities", 900, 3400),
    ("MSEDCL Bill Pay", "Utilities", 850, 3200),
    ("Adani Electricity Mumbai", "Utilities", 1100, 3800),
    ("Jio Prepaid Recharge", "Recharge", 299, 799),
    ("Airtel Prepaid", "Recharge", 299, 699),
    ("ACT Fibernet", "Utilities", 799, 1499),
    ("Airtel Xstream Fiber", "Utilities", 999, 1599),
)

_ENT = (
    ("BookMyShow", "Entertainment", 350, 2200),
    ("PVR Cinemas", "Entertainment", 400, 1800),
    ("Steam Purchase", "Entertainment", 500, 3200),
    ("Insider.in Events", "Entertainment", 800, 5200),
)

_HEALTH = (
    ("PharmEasy", "Health", 250, 2200),
    ("Netmeds", "Health", 200, 1800),
    ("Apollo Pharmacy", "Health", 150, 1600),
    ("Practo Consult", "Health", 350, 1500),
    ("Thyrocare Labs", "Health", 900, 5200),
)

_FEST_MERCH = (
    ("Myntra Diwali Sale", "Shopping", "diwali"),
    ("Amazon Great Indian Festival", "Shopping", "diwali"),
    ("Local Sweet Shop", "Food", "diwali"),
    ("Reliance Smart Dussehra", "Groceries", "dussehra"),
    ("Big Bazaar Holi", "Shopping", "holi"),
    ("MakeMyTrip NY Travel", "Travel", "new_year"),
)

_MISC = (
    ("Urban Company", "Utilities", 400, 2200),
    ("Insurance LIC Premium", "Bills", 2500, 18_000),
    ("ICICI Lombard Health", "Health", 1200, 8500),
    ("Mutual Fund SIP HDFC", "Investment", 5000, 25_000),
)


def _pick_bracket(rnd: random.Random) -> tuple[int, int, str]:
    r = rnd.random()
    if r < 0.25:
        lo, hi = _BRACKET_ENTRY
        ag = rnd.choice(["22-28", "22-28", "28-35"])
    elif r < 0.65:
        lo, hi = _BRACKET_MID
        ag = rnd.choice(["22-28", "28-35", "35-45"])
    elif r < 0.90:
        lo, hi = _BRACKET_SENIOR
        ag = rnd.choice(["28-35", "35-45", "45-55"])
    else:
        lo, hi = _BRACKET_EXEC
        ag = rnd.choice(["35-45", "45-55"])
    return lo, hi, ag


def _tier_for_income(rnd: random.Random, income_hi: int) -> int:
    if income_hi <= 45_000:
        return rnd.choices([2, 3], weights=[0.55, 0.45])[0]
    if income_hi <= 90_000:
        return rnd.choices([1, 2, 3], weights=[0.35, 0.45, 0.20])[0]
    return rnd.choices([1, 2], weights=[0.72, 0.28])[0]


def _lifestyle(lo: int, hi: int) -> str:
    mid = (lo + hi) / 2
    if mid < 45_000:
        return "budget"
    if mid < 100_000:
        return "moderate"
    return "premium"


def _seed_row(
    *,
    category: str,
    subcategory: str,
    merchant_name: str,
    amount: float,
    transaction_type: str,
    description: str,
    frequency: str | None,
    day_of_month: int | None,
    typical_hour: int | None,
    min_income: float | None,
    max_income: float | None,
    age_group: str | None,
    city_tier: int | None,
    lifestyle: str | None,
    is_emi: bool,
    is_subscription: bool,
    is_fraud_pattern: bool,
    fraud_type: str | None,
    seasonal_tag: str | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "subcategory": subcategory,
        "merchant_name": merchant_name,
        "amount": Decimal(str(round(amount, 2))),
        "transaction_type": transaction_type,
        "description": description,
        "frequency": frequency,
        "day_of_month": day_of_month,
        "typical_hour": typical_hour,
        "min_income": Decimal(str(min_income)) if min_income is not None else None,
        "max_income": Decimal(str(max_income)) if max_income is not None else None,
        "age_group": age_group,
        "city_tier": city_tier,
        "lifestyle": lifestyle,
        "is_emi": is_emi,
        "is_subscription": is_subscription,
        "is_fraud_pattern": is_fraud_pattern,
        "fraud_type": fraud_type,
        "seasonal_tag": seasonal_tag,
    }


def _gen_income(n: int, rnd: random.Random) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _ in range(n):
        lo, hi, ag = _pick_bracket(rnd)
        tier = _tier_for_income(rnd, hi)
        amt = rnd.randint(lo, hi)
        company = rnd.choice(_COMPANIES)
        row = _seed_row(
            category="income",
            subcategory="salary",
            merchant_name=f"Salary Credit — {company}",
            amount=float(amt),
            transaction_type="CREDIT",
            description="Monthly salary NEFT",
            frequency="monthly",
            day_of_month=rnd.randint(1, 5),
            typical_hour=rnd.choice([0, 1, 2, 8, 9]),
            min_income=float(lo * 0.85),
            max_income=float(hi * 1.15),
            age_group=ag,
            city_tier=tier,
            lifestyle=_lifestyle(lo, hi),
            is_emi=False,
            is_subscription=False,
            is_fraud_pattern=False,
            fraud_type=None,
        )
        out.append(row)
    return out


def _gen_emi(n: int, rnd: random.Random) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    pools = (
        ("home", _EMI_HOME, 15_000, 62_000, 55_000),
        ("car", _EMI_CAR, 12_000, 30_000, 45_000),
        ("bike", _EMI_BIKE, 3_000, 8_000, 28_000),
        ("personal", _EMI_PL, 5_000, 20_000, 32_000),
    )
    for _ in range(n):
        kind, merch_pool, a_lo, a_hi, min_inc = rnd.choice(pools)
        m = rnd.choice(merch_pool)
        amt = rnd.randint(a_lo, a_hi)
        lo, hi = int(min_inc * 0.7), int(min_inc * 4.5)
        ag = rnd.choice(["28-35", "35-45", "45-55", "22-28"])
        tier = rnd.choice([1, 1, 2, 3])
        out.append(
            _seed_row(
                category="emi",
                subcategory=f"{kind}_loan",
                merchant_name=m,
                amount=float(amt),
                transaction_type="DEBIT",
                description=f"{kind.title()} loan EMI NACH",
                frequency="monthly",
                day_of_month=rnd.randint(1, 15),
                typical_hour=rnd.randint(6, 11),
                min_income=float(lo),
                max_income=float(hi),
                age_group=ag,
                city_tier=tier,
                lifestyle=rnd.choice(["moderate", "premium"]),
                is_emi=True,
                is_subscription=False,
                is_fraud_pattern=False,
                fraud_type=None,
            )
        )
    return out


def _gen_subscription(n: int, rnd: random.Random) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _ in range(n):
        name, base, cat = rnd.choice(_SUBS)
        amt = float(rnd.choice([base, int(base * 0.85), int(base * 1.05)]))
        lo, hi, ag = _pick_bracket(rnd)
        tier = _tier_for_income(rnd, hi)
        out.append(
            _seed_row(
                category="subscription",
                subcategory="ott_or_saas",
                merchant_name=name,
                amount=amt,
                transaction_type="DEBIT",
                description="Auto-debit subscription renewal",
                frequency="monthly",
                day_of_month=rnd.randint(1, 28),
                typical_hour=rnd.randint(8, 22),
                min_income=float(lo * 0.5),
                max_income=float(hi * 1.2),
                age_group=ag,
                city_tier=tier,
                lifestyle=_lifestyle(lo, hi),
                is_emi=False,
                is_subscription=True,
                is_fraud_pattern=False,
                fraud_type=None,
            )
        )
    return out


def _scatter_amount(rnd: random.Random, lo: int, hi: int) -> float:
    return float(rnd.randint(lo, hi))


def _gen_simple_pool(
    n: int,
    rnd: random.Random,
    *,
    category: str,
    sub_key: str,
    pool: tuple[tuple[str, str, int, int], ...],
    freq: str,
    is_sub: bool = False,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _ in range(n):
        merchant, sub, lo, hi = rnd.choice(pool)
        lo_i, hi_i, ag = _pick_bracket(rnd)
        tier = _tier_for_income(rnd, hi_i)
        out.append(
            _seed_row(
                category=category,
                subcategory=sub_key,
                merchant_name=merchant,
                amount=_scatter_amount(rnd, lo, hi),
                transaction_type="DEBIT",
                description=f"{merchant} — {sub}",
                frequency=freq,
                day_of_month=rnd.randint(1, 28) if freq == "monthly" else None,
                typical_hour=rnd.choice(list(range(9, 23))),
                min_income=float(lo_i * 0.4),
                max_income=float(hi_i * 1.25),
                age_group=ag,
                city_tier=tier,
                lifestyle=_lifestyle(lo_i, hi_i),
                is_emi=False,
                is_subscription=is_sub,
                is_fraud_pattern=False,
                fraud_type=None,
            )
        )
    return out


def _gen_festival(n: int, rnd: random.Random) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _ in range(n):
        merchant, cat, tag = rnd.choice(_FEST_MERCH)
        amt = _scatter_amount(rnd, 500, 22_000 if tag == "diwali" else 8000)
        lo, hi, ag = _pick_bracket(rnd)
        tier = _tier_for_income(rnd, hi)
        out.append(
            _seed_row(
                category="festival",
                subcategory=tag,
                merchant_name=merchant,
                amount=amt,
                transaction_type="DEBIT",
                description=f"Seasonal spend ({tag})",
                frequency="seasonal",
                day_of_month=None,
                typical_hour=rnd.randint(12, 21),
                min_income=float(lo * 0.5),
                max_income=float(hi * 1.3),
                age_group=ag,
                city_tier=tier,
                lifestyle=_lifestyle(lo, hi),
                is_emi=False,
                is_subscription=False,
                is_fraud_pattern=False,
                fraud_type=None,
                seasonal_tag=tag,
            )
        )
    return out


def _gen_fraud(n: int, rnd: random.Random) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    i = 0
    while len(out) < n and i < n + 50:
        i += 1
        if len(out) + 2 <= n and rnd.random() < 0.55:
            m = rnd.choice(("VERIFY UPI ID XX8821", "CARD CHECK MERCHANT", "UNKNOWN UPI VERIFY"))
            lo, hi, ag = _pick_bracket(rnd)
            tier = _tier_for_income(rnd, hi)
            small = float(rnd.choice([1, 2, 3, 5]))
            big = float(rnd.randint(5000, 48_000))
            common = dict(
                category="fraud",
                subcategory="one_rupee_trap",
                merchant_name=m,
                transaction_type="DEBIT",
                frequency="random",
                day_of_month=None,
                typical_hour=rnd.randint(10, 22),
                min_income=float(lo * 0.5),
                max_income=float(hi * 1.2),
                age_group=ag,
                city_tier=tier,
                lifestyle=_lifestyle(lo, hi),
                is_emi=False,
                is_subscription=False,
                is_fraud_pattern=True,
                fraud_type="one_rupee_trap",
            )
            out.append(_seed_row(**common, amount=small, description="Verification debit"))
            out.append(_seed_row(**common, amount=big, description="Follow-up subscription or annual fee"))
        elif len(out) + 2 <= n:
            merchant = rnd.choice(("BookMyShow", "Swiggy", "Amazon India", "Flipkart"))
            amt = float(rnd.randint(500, 12_000))
            lo, hi, ag = _pick_bracket(rnd)
            tier = _tier_for_income(rnd, hi)
            common = dict(
                category="fraud",
                subcategory="duplicate_charge",
                merchant_name=merchant,
                amount=amt,
                transaction_type="DEBIT",
                description="Duplicate charge pattern",
                frequency="random",
                day_of_month=None,
                typical_hour=rnd.randint(11, 20),
                min_income=float(lo * 0.5),
                max_income=float(hi * 1.2),
                age_group=ag,
                city_tier=tier,
                lifestyle=_lifestyle(lo, hi),
                is_emi=False,
                is_subscription=False,
                is_fraud_pattern=True,
                fraud_type="duplicate",
            )
            out.append(_seed_row(**common))
            out.append(_seed_row(**common))
        else:
            break
    return out[:n]


def _scale_counts(total: int) -> dict[str, int]:
    base = sum(_COUNTS.values())
    raw: dict[str, int] = {}
    keys = list(_COUNTS.keys())
    acc = 0
    for i, k in enumerate(keys):
        if i == len(keys) - 1:
            raw[k] = max(1, total - acc)
        else:
            v = max(1, int(round(_COUNTS[k] * total / base)))
            raw[k] = v
            acc += v
    drift = total - sum(raw.values())
    idx = 0
    while drift != 0 and idx < 100000:
        k = keys[idx % len(keys)]
        if drift > 0:
            raw[k] += 1
            drift -= 1
        else:
            if raw[k] > 1:
                raw[k] -= 1
                drift += 1
        idx += 1
    return raw


def generate_seed_corpus_rows(*, total: int = _DEFAULT_TOTAL, seed: int = 42) -> list[dict[str, Any]]:
    """
    Build ``total`` template rows for ``transaction_seed_data`` (default 26_000).

    Rows are deterministic for a fixed ``seed`` (useful for reproducible CSV/DB loads).
    """
    rnd = random.Random(seed)
    c = _scale_counts(total)
    rows: list[dict[str, Any]] = []
    rows.extend(_gen_income(c["income"], rnd))
    rows.extend(_gen_emi(c["emi"], rnd))
    rows.extend(_gen_subscription(c["subscription"], rnd))
    rows.extend(_gen_simple_pool(c["food"], rnd, category="food", sub_key="dining", pool=_FOOD, freq="random"))
    rows.extend(_gen_simple_pool(c["transport"], rnd, category="transport", sub_key="mobility", pool=_TRANSPORT, freq="random"))
    rows.extend(_gen_simple_pool(c["shopping"], rnd, category="shopping", sub_key="retail", pool=_SHOPPING, freq="random"))
    rows.extend(_gen_simple_pool(c["utility"], rnd, category="utility", sub_key="bills", pool=_UTILITY, freq="monthly"))
    rows.extend(_gen_simple_pool(c["entertainment"], rnd, category="entertainment", sub_key="leisure", pool=_ENT, freq="random"))
    rows.extend(_gen_simple_pool(c["health"], rnd, category="health", sub_key="wellness", pool=_HEALTH, freq="random"))
    rows.extend(_gen_festival(c["festival"], rnd))
    rows.extend(_gen_fraud(c["fraud"], rnd))
    rows.extend(_gen_simple_pool(c["misc"], rnd, category="misc", sub_key="general", pool=_MISC, freq="random"))
    rnd.shuffle(rows)
    return rows[:total]


def corpus_validation_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Lightweight sanity stats for QA."""
    deb = sum(1 for r in rows if r["transaction_type"] == "DEBIT")
    cred = len(rows) - deb
    emi = sum(1 for r in rows if r.get("is_emi"))
    sub = sum(1 for r in rows if r.get("is_subscription"))
    fraud = sum(1 for r in rows if r.get("is_fraud_pattern"))
    amounts = [float(r["amount"]) for r in rows]
    return {
        "count": len(rows),
        "debits": deb,
        "credits": cred,
        "emi_templates": emi,
        "subscription_templates": sub,
        "fraud_templates": fraud,
        "amount_min": min(amounts) if amounts else 0,
        "amount_max": max(amounts) if amounts else 0,
        "reference_date": date.today().isoformat(),
    }
