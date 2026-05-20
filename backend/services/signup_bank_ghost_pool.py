"""
Seven pre-built lifestyle transaction pools for signup bank linking.

Each pool user (IDs 900001–900007) holds ~12–18 months of realistic Indian day-to-day
spends. On bank link we clone that pool onto the new signup user and personalize
descriptions with their display name — same idea as legacy ghost1–ghost5 (user ids 6–10).
"""

from __future__ import annotations

import calendar
import logging
import random
from datetime import date, datetime, time, timedelta
from typing import Any

from services.new_user_transaction_seed import (
    _fetch_transaction_columns,
    bulk_insert_transaction_dicts,
    insert_individual_transactions,
)
from services.transaction_enrichment import (
    latest_transaction_period,
    sync_all_monthly_summaries_for_user,
)

logger = logging.getLogger(__name__)

# Reserved internal pool IDs — do not overlap real signups.
POOL_BASE_ID = 900_001

SIGNUP_GHOST_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "bank_slug": "HDFC",
        "pool_user_id": POOL_BASE_ID + 0,
        "email": "signup_ghost_hdfc@pool.smartspend.internal",
        "persona_name": "Arjun Patel",
        "occupation": "Software Developer",
        "city": "Hyderabad",
        "monthly_income": 52_000,
        "bank_label": "HDFC Bank",
        "rent": 12_000,
        "rent_merchant": "Madhapur Flat Owner",
        "lifestyle": "IT professional — bike EMI, Swiggy lunches, weekend PVR",
    },
    {
        "bank_slug": "SBI",
        "pool_user_id": POOL_BASE_ID + 1,
        "email": "signup_ghost_sbi@pool.smartspend.internal",
        "persona_name": "Priya Nair",
        "occupation": "Staff Nurse",
        "city": "Kochi",
        "monthly_income": 48_000,
        "bank_label": "State Bank of India",
        "rent": 9_500,
        "rent_merchant": "Kakkanad PG Hostel",
        "lifestyle": "Shift worker — hospital canteen, bus commute, family remittance",
    },
    {
        "bank_slug": "ICICI",
        "pool_user_id": POOL_BASE_ID + 2,
        "email": "signup_ghost_icici@pool.smartspend.internal",
        "persona_name": "Kavya Reddy",
        "occupation": "Operations Manager",
        "city": "Kolkata",
        "monthly_income": 88_000,
        "bank_label": "ICICI Bank",
        "rent": 22_000,
        "rent_merchant": "Salt Lake Housing",
        "lifestyle": "Dual EMI (car + education), Netflix, BigBasket, metro",
    },
    {
        "bank_slug": "AXIS",
        "pool_user_id": POOL_BASE_ID + 3,
        "email": "signup_ghost_axis@pool.smartspend.internal",
        "persona_name": "Rohan Mehta",
        "occupation": "Chartered Accountant",
        "city": "Ahmedabad",
        "monthly_income": 62_000,
        "bank_label": "Axis Bank",
        "rent": 13_500,
        "rent_merchant": "Navrangpura Society",
        "lifestyle": "Phone EMI, AMTS bus + Ola, chai stalls, Flipkart gadgets",
    },
    {
        "bank_slug": "KOTAK",
        "pool_user_id": POOL_BASE_ID + 4,
        "email": "signup_ghost_kotak@pool.smartspend.internal",
        "persona_name": "Siddharth Joshi",
        "occupation": "Government Clerk",
        "city": "Lucknow",
        "monthly_income": 55_000,
        "bank_label": "Kotak Mahindra Bank",
        "rent": 11_000,
        "rent_merchant": "Gomti Nagar Landlord",
        "lifestyle": "Furniture EMI, Zepto groceries, Hotstar, auto rickshaw",
    },
    {
        "bank_slug": "PNB",
        "pool_user_id": POOL_BASE_ID + 5,
        "email": "signup_ghost_pnb@pool.smartspend.internal",
        "persona_name": "Neha Gupta",
        "occupation": "Junior Analyst",
        "city": "Jaipur",
        "monthly_income": 28_000,
        "bank_label": "Punjab National Bank",
        "rent": 5_000,
        "rent_merchant": "Vaishali Nagar PG",
        "lifestyle": "Budget PG life — RSRTC bus, Meesho, Raj Mandir cinema",
    },
    {
        "bank_slug": "BOB",
        "pool_user_id": POOL_BASE_ID + 6,
        "email": "signup_ghost_bob@pool.smartspend.internal",
        "persona_name": "Amit Desai",
        "occupation": "Textile Trader",
        "city": "Surat",
        "monthly_income": 72_000,
        "bank_label": "Bank of Baroda",
        "rent": 15_000,
        "rent_merchant": "Ring Road Shop + Home",
        "lifestyle": "UPI-heavy trader — wholesale market, petrol, family dining",
    },
)

# Display names for banks shown in onboarding — any slug/name is accepted.
KNOWN_BANK_LABELS: dict[str, str] = {
    "HDFC": "HDFC Bank",
    "SBI": "State Bank of India",
    "ICICI": "ICICI Bank",
    "AXIS": "Axis Bank",
    "KOTAK": "Kotak Mahindra Bank",
    "PNB": "Punjab National Bank",
    "BOB": "Bank of Baroda",
    "YES": "Yes Bank",
    "IDBI": "IDBI Bank",
    "CANARA": "Canara Bank",
    "UNION": "Union Bank of India",
    "INDUSIND": "IndusInd Bank",
    "FEDERAL": "Federal Bank",
    "BANDHAN": "Bandhan Bank",
}


def resolve_bank_label(
    bank_slug: str | None = None,
    bank_name: str | None = None,
) -> tuple[str, str]:
    """
    Map any onboarding bank choice to a display label.
    Pools are bank-free; only the user's selected name is shown after link.
    """
    name = (bank_name or "").strip()
    if name:
        slug = (bank_slug or "").strip().upper() or name.split()[0].upper()[:24]
        return slug, name
    slug = (bank_slug or "").strip().upper()
    if slug in KNOWN_BANK_LABELS:
        return slug, KNOWN_BANK_LABELS[slug]
    if not slug:
        return "BANK", "Linked Bank Account"
    pretty = slug.replace("_", " ").title()
    if "BANK" in pretty.upper():
        return slug, pretty
    return slug, f"{pretty} Bank"


def pick_persona_profile(user_id: int) -> dict[str, Any]:
    """Stable lifestyle pool per user — independent of which bank they tap."""
    idx = int(user_id) % len(SIGNUP_GHOST_PROFILES)
    return SIGNUP_GHOST_PROFILES[idx]


def _all_ghost_persona_names() -> tuple[str, ...]:
    return tuple(str(p["persona_name"]) for p in SIGNUP_GHOST_PROFILES)


def _all_template_bank_labels() -> tuple[str, ...]:
    return tuple(str(p["bank_label"]) for p in SIGNUP_GHOST_PROFILES)


def _replace_ghost_identity_in_text(
    text: str,
    *,
    display_name: str,
    bank_label: str,
) -> str:
    """Strip every internal ghost persona/bank label — show only the signup user."""
    out = text
    for name in _all_ghost_persona_names():
        if name:
            out = out.replace(name, display_name)
    for label in _all_template_bank_labels():
        if label:
            out = out.replace(label, bank_label)
    return out


def _personalize_transaction_record(
    rec: dict[str, Any],
    profile: dict[str, Any],
    *,
    display_name: str,
    bank_label: str,
) -> None:
    """Rewrite ghost pool text → signup user's name and their chosen bank only."""
    for field in ("description", "merchant"):
        if field not in rec or rec[field] is None:
            continue
        text = _replace_ghost_identity_in_text(
            str(rec[field]), display_name=display_name, bank_label=bank_label
        )
        rec[field] = text
    if "bank_name" in rec:
        rec["bank_name"] = bank_label
    cat = str(rec.get("category") or "").lower()
    typ = str(rec.get("type") or "").upper()
    desc = str(rec.get("description") or "").lower()
    if typ == "CREDIT" and (cat == "salary" or "salary" in desc):
        rec["description"] = f"NEFT Salary Credit — {display_name}"


def scrub_user_account_identity(
    cur: Any,
    user_id: int,
    *,
    display_name: str,
    bank_label: str,
) -> int:
    """
    Final pass: no ghost persona names remain on this user's rows.
    Pool data is anonymous; only the linked member's name is visible.
    """
    names = _all_ghost_persona_names()
    banks = _all_template_bank_labels()
    updated = 0

    cur.execute(
        "UPDATE users SET name = %s, bank = %s WHERE id = %s",
        (display_name[:100], bank_label[:50], user_id),
    )

    for name in names:
        if not name:
            continue
        cur.execute(
            """
            UPDATE transactions
            SET description = REPLACE(COALESCE(description, ''), %s, %s),
                merchant = REPLACE(COALESCE(merchant, ''), %s, %s)
            WHERE user_id = %s
            """,
            (name, display_name, name, display_name, user_id),
        )
        updated += int(cur.rowcount or 0)
    for label in banks:
        if not label:
            continue
        cur.execute(
            """
            UPDATE transactions
            SET bank_name = %s,
                merchant = CASE WHEN merchant = %s THEN %s ELSE merchant END
            WHERE user_id = %s AND (bank_name = %s OR merchant = %s)
            """,
            (bank_label, label, bank_label, user_id, label, label),
        )
    if banks:
        cur.execute(
            """
            UPDATE transactions
            SET bank_name = %s
            WHERE user_id = %s
              AND (bank_name IS NULL OR bank_name = '' OR bank_name = ANY(%s))
            """,
            (bank_label, user_id, list(banks)),
        )
    cur.execute(
        """
        UPDATE transactions
        SET description = %s
        WHERE user_id = %s AND type = 'CREDIT'
          AND LOWER(COALESCE(category, '')) = 'salary'
        """,
        (f"NEFT Salary Credit — {display_name}", user_id),
    )
    return updated


def ghost_pool_summary() -> list[dict[str, Any]]:
    """Human-readable summary for docs / admin."""
    out: list[dict[str, Any]] = []
    for i, p in enumerate(SIGNUP_GHOST_PROFILES):
        out.append(
            {
                "pool_index": i + 1,
                "pool_user_id": p["pool_user_id"],
                "persona": p["persona_name"],
                "city": p["city"],
                "occupation": p["occupation"],
                "monthly_income_inr": p["monthly_income"],
                "lifestyle_note": p["lifestyle"],
                "works_with_any_bank": True,
            }
        )
    return out


def _month_starts(start: date, end: date) -> list[date]:
    cur = date(start.year, start.month, 1)
    out: list[date] = []
    while cur <= end:
        out.append(cur)
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return out


def _last_day_of_month(m: date, cap: date) -> date:
    _, dim = calendar.monthrange(m.year, m.month)
    last = date(m.year, m.month, dim)
    return min(last, cap)


def _festival_multiplier(month: int) -> float:
    if month == 10:
        return 1.65
    if month == 3:
        return 1.22
    if month == 4:
        return 1.12
    if month == 12:
        return 1.18
    return 1.0


def _generate_pool_transactions(cur: Any, profile: dict[str, Any]) -> int:
    """Build ~12–18 months of salary, rent, utilities, food, transport, shopping."""
    uid = int(profile["pool_user_id"])
    rnd = random.Random(uid * 17_389 + 42)
    cols = _fetch_transaction_columns(cur)
    if not cols:
        return 0

    start = date(2024, 12, 1)
    end = date(2026, 5, 14)
    income = float(profile["monthly_income"])
    bank = str(profile["bank_label"])
    city = str(profile["city"])
    rent = float(profile["rent"])
    rent_m = str(profile["rent_merchant"])

    specs: list[dict[str, Any]] = []

    for m_start in _month_starts(start, end):
        mo = m_start.month
        vf = _festival_multiplier(mo)
        vx = 0.88 + ((mo * 7 + uid) % 25) / 100.0
        last = _last_day_of_month(m_start, end)

        def add(day_off: int, hour: int, minute: int, amount: float, typ: str, merch: str, cat: str, desc: str):
            d = m_start + timedelta(days=day_off)
            if d > last:
                return
            specs.append(
                {
                    "transaction_date": d,
                    "transaction_time": time(hour, minute, 0),
                    "amount": round(amount * vx, 2) if typ == "DEBIT" else round(amount, 2),
                    "merchant": merch,
                    "category": cat,
                    "type": typ,
                    "description": desc,
                }
            )

        salary = min(income, 99_000.0)
        add(0, 9, 0, salary, "CREDIT", bank, "salary", "NEFT Salary Credit")
        add(1, 10, 0, rent, "DEBIT", rent_m, "rent", f"Monthly Rent — {city}")
        elec = 800 if income < 40_000 else (1200 if income < 70_000 else 1800)
        if mo in (4, 5, 6, 7, 8):
            elec *= 1.25
        add(2, 11, 0, elec, "DEBIT", "Electricity Board", "utilities", f"Electricity — {city}")
        add(3, 11, 30, 499 if income > 50_000 else 199, "DEBIT", "Broadband", "utilities", "Internet / mobile plan")

        idx = int(profile["pool_user_id"]) - POOL_BASE_ID
        if idx == 2 and m_start >= date(2025, 7, 1):
            add(4, 9, 0, 14_850, "DEBIT", bank, "emi", "EMI NACH — Maruti Swift")
            add(4, 9, 10, 9_800, "DEBIT", bank, "emi", "EMI ECS — Education loan")
        elif idx == 0 and m_start >= date(2025, 3, 1):
            add(4, 9, 0, 2_799, "DEBIT", bank, "emi", "EMI NACH — Bike loan")
        elif idx == 3 and m_start >= date(2026, 1, 1):
            add(4, 9, 0, 3_899, "DEBIT", bank, "emi", "EMI AutoDebit — Mobile")
        elif idx == 4 and m_start >= date(2025, 9, 1):
            add(4, 9, 0, 2_499, "DEBIT", bank, "emi", "EMI NACH — Furniture")
        elif idx == 6 and m_start >= date(2024, 6, 1):
            add(4, 9, 0, 6_850, "DEBIT", bank, "emi", "EMI ECS — Commercial vehicle")
        elif idx == 1 and m_start >= date(2025, 6, 1):
            add(4, 9, 0, 3_199, "DEBIT", bank, "emi", "EMI NACH — Scooter loan")

        subs: list[tuple[int, float, str, str]] = []
        if income >= 80_000:
            subs = [(5, 649, "Netflix", "subscription"), (10, 119, "Spotify", "subscription")]
        elif income >= 45_000:
            subs = [(5, 299, "Hotstar", "subscription"), (13, 149, "Swiggy One", "subscription")]
        else:
            subs = [(17, 119, "Spotify", "subscription")]
        for day, amt, merch, cat in subs:
            add(day, 8, 0, amt, "DEBIT", merch, cat, f"{merch} subscription")

        food_merchants = ("Swiggy", "Zomato")
        food_days = [2, 5, 8, 11, 14, 17, 20, 23, 26]
        for i, day in enumerate(food_days):
            base = 180 + (i % 4) * 70
            if income < 35_000:
                base = 120 + (i % 3) * 40
            merch = food_merchants[i % 2]
            add(day, 13, 15, base * vf, "DEBIT", merch, "food_delivery", f"Food order — {merch}")

        transport: list[tuple[int, str, float]] = []
        if city in ("Hyderabad", "Kolkata", "Delhi", "Mumbai"):
            transport = [(4, "Metro", 55), (7, "Ola Cabs", 180), (12, "Uber", 160), (18, "Ola Cabs", 210)]
        elif city == "Jaipur":
            transport = [(3, "RSRTC Bus", 45), (6, "Auto Rickshaw", 80), (11, "RSRTC Bus", 45), (16, "Auto Rickshaw", 75)]
        else:
            transport = [(4, "Ola Cabs", 150), (9, "Rapido", 85), (15, "Ola Cabs", 165), (22, "Auto Rickshaw", 70)]
        for day, merch, base in transport:
            add(day, 9, 30, base, "DEBIT", merch, "transport", f"Commute — {merch}")

        groceries = [
            (4, "BigBasket", 1_350),
            (10, "DMart", 1_200),
            (16, "Zepto", 1_050),
            (22, "Reliance Smart", 1_100),
        ]
        if income < 35_000:
            groceries = [(5, "Local Kirana", 650), (12, "Reliance Smart", 720), (19, "Zepto", 700)]
        for day, merch, base in groceries:
            add(day, 11, 0, base * vf, "DEBIT", merch, "groceries", f"Grocery — {merch}")

        shopping_days = [(7, "Amazon", 1_200), (18, "Flipkart", 950)]
        if income >= 80_000:
            shopping_days.append((24, "Myntra", 2_800))
        for day, merch, base in shopping_days:
            add(day, 15, 0, base * vf, "DEBIT", merch, "shopping", f"Shopping — {merch}")

        if mo % 2 == 0:
            add(12, 12, 0, 480 if income < 50_000 else 900, "DEBIT", "Apollo Pharmacy", "medical", "Medical / pharmacy")
        if mo % 3 == 1:
            add(19, 19, 0, 450 if income < 50_000 else 800, "DEBIT", "PVR / INOX", "entertainment", "Weekend outing")
        if income >= 60_000 and mo % 2 == 1:
            add(8, 8, 30, 1_600, "DEBIT", "Petrol Pump", "petrol", "Fuel")

    n = insert_individual_transactions(cur, uid, specs)
    logger.info("Generated %s pool transactions for ghost user_id=%s (%s)", n, uid, profile["bank_slug"])
    return n


def _ensure_pool_user(cur: Any, profile: dict[str, Any]) -> None:
    uid = int(profile["pool_user_id"])
    cur.execute("SELECT id FROM users WHERE id = %s", (uid,))
    if cur.fetchone():
        return
    cur.execute(
        """
        INSERT INTO users (
          id, email, password_hash, name, monthly_income, bank, city,
          onboarding_completed, is_verified
        )
        OVERRIDING SYSTEM VALUE
        VALUES (%s, %s, '$2a$10$disabled', %s, %s, %s, %s, TRUE, FALSE)
        """,
        (
            uid,
            profile["email"],
            profile["persona_name"],
            profile["monthly_income"],
            profile["bank_slug"],
            profile["city"],
        ),
    )


def ensure_signup_ghost_pool_seeded(cur: Any) -> int:
    """Create all seven pool users and transactions if missing."""
    generated = 0
    for profile in SIGNUP_GHOST_PROFILES:
        _ensure_pool_user(cur, profile)
        uid = int(profile["pool_user_id"])
        cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id = %s", (uid,))
        cnt = int(cur.fetchone()[0] or 0)
        if cnt < 200:
            generated += _generate_pool_transactions(cur, profile)
    return generated


def _cloneable_columns(cur: Any) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'transactions'
          AND column_name NOT IN ('id')
        ORDER BY ordinal_position
        """
    )
    return [str(r[0]) for r in cur.fetchall()]


def _rebrand_existing_ghost_transactions(
    cur: Any,
    user_id: int,
    profile: dict[str, Any],
    *,
    display_name: str,
    bank_label: str,
) -> int:
    """If user already linked, relabel to their name + newly chosen bank."""
    del profile  # bank-free rebrand uses full ghost name list
    return scrub_user_account_identity(
        cur, user_id, display_name=display_name, bank_label=bank_label
    )


def link_signup_bank_ghost(
    conn: Any,
    cur: Any,
    *,
    user_id: int,
    bank_slug: str,
    display_name: str,
    bank_name: str | None = None,
    account_last4: str | None = None,
) -> dict[str, Any]:
    """
    Clone a lifestyle pool onto ``user_id`` and label everything with the bank
    the user actually selected (bank-free pools).
    """
    slug, bank_label = resolve_bank_label(bank_slug, bank_name)
    profile = pick_persona_profile(user_id)
    ensure_signup_ghost_pool_seeded(cur)
    ghost_id = int(profile["pool_user_id"])
    mask = (account_last4 or "4821").strip()[-4:] or "4821"
    mask = f"****{mask}"

    cur.execute(
        """
        SELECT id FROM connected_sources
        WHERE user_id = %s AND added_via = 'signup_ghost_link'
        LIMIT 1
        """,
        (user_id,),
    )
    existing_link = cur.fetchone()

    cur.execute(
        """
        SELECT COUNT(*) FROM transactions
        WHERE user_id = %s AND COALESCE(data_origin, '') = 'signup_ghost_link'
        """,
        (user_id,),
    )
    already = int(cur.fetchone()[0] or 0)

    linked = 0
    rebranded = 0
    if already >= 50:
        rebranded = _rebrand_existing_ghost_transactions(
            cur, user_id, profile, display_name=display_name, bank_label=bank_label
        )
    elif already < 50:
        col_list = _cloneable_columns(cur)
        if not col_list:
            raise RuntimeError("transactions table has no columns")
        col_sql = ", ".join(col_list)
        cur.execute(
            f"SELECT {col_sql} FROM transactions WHERE user_id = %s ORDER BY transaction_date, id",
            (ghost_id,),
        )
        ghost_rows = cur.fetchall()
        cur.execute(
            """
            SELECT transaction_date, amount, merchant, type
            FROM transactions WHERE user_id = %s
            """,
            (user_id,),
        )
        existing_keys = {
            (str(r[0]), float(r[1] or 0), str(r[2] or ""), str(r[3] or ""))
            for r in cur.fetchall()
        }
        to_insert: list[dict[str, Any]] = []
        for row in ghost_rows:
            rec = dict(zip(col_list, row))
            key = (
                str(rec.get("transaction_date")),
                float(rec.get("amount") or 0),
                str(rec.get("merchant") or ""),
                str(rec.get("type") or ""),
            )
            if key in existing_keys:
                continue
            rec["user_id"] = user_id
            _personalize_transaction_record(
                rec, profile, display_name=display_name, bank_label=bank_label
            )
            if "data_origin" in col_list:
                rec["data_origin"] = "signup_ghost_link"
            to_insert.append(rec)
        if to_insert:
            linked = bulk_insert_transaction_dicts(cur, to_insert)

    try:
        cur.execute(
            """
            INSERT INTO connected_sources (
              user_id, source_type, institution_name, account_number_masked,
              is_primary, is_visible_on_dashboard, added_via, status, is_ghost
            )
            VALUES (%s, 'bank', %s, %s, TRUE, TRUE, 'signup_ghost_link', 'active', FALSE)
            ON CONFLICT ON CONSTRAINT connected_sources_user_inst_type_key DO UPDATE
              SET status = 'active',
                  is_primary = TRUE,
                  is_visible_on_dashboard = TRUE,
                  account_number_masked = EXCLUDED.account_number_masked,
                  added_via = 'signup_ghost_link'
            """,
            (user_id, bank_label, mask),
        )
    except Exception:
        cur.execute(
            """
            INSERT INTO connected_sources (
              user_id, source_type, institution_name, account_number_masked,
              is_primary, is_visible_on_dashboard, added_via, status
            )
            SELECT %s, 'bank', %s, %s, TRUE, TRUE, 'signup_ghost_link', 'active'
            WHERE NOT EXISTS (
              SELECT 1 FROM connected_sources
              WHERE user_id = %s AND institution_name = %s AND source_type = 'bank'
            )
            """,
            (user_id, bank_label, mask, user_id, bank_label),
        )

    cur.execute(
        """
        SELECT 1 FROM bank_connections WHERE user_id = %s AND bank_name = %s LIMIT 1
        """,
        (user_id, bank_label),
    )
    if not cur.fetchone():
        cur.execute(
            """
            INSERT INTO bank_connections (user_id, bank_name, account_masked)
            VALUES (%s, %s, %s)
            """,
            (user_id, bank_label, mask),
        )

    cur.execute(
        "UPDATE users SET bank = %s, dashboard_mode = 'bank_only' WHERE id = %s",
        (slug[:20], user_id),
    )

    workspace_stats: dict[str, Any] = {}
    try:
        from services.signup_ghost_workspace import seed_signup_ghost_workspace

        workspace_stats = seed_signup_ghost_workspace(
            cur,
            user_id,
            profile,
            bank_label=bank_label,
            display_name=display_name,
        )
    except Exception as ws_exc:  # noqa: BLE001
        logger.warning("signup workspace seed skipped user_id=%s: %s", user_id, ws_exc)

    scrub_user_account_identity(
        cur, user_id, display_name=display_name, bank_label=bank_label
    )

    sync_all_monthly_summaries_for_user(conn, user_id)

    period = latest_transaction_period(conn, user_id)
    sy, sm = (period if period else (None, None))

    cur.execute(
        """
        SELECT transaction_date, merchant, amount, type, category
        FROM transactions
        WHERE user_id = %s
        ORDER BY transaction_date DESC, id DESC
        LIMIT 12
        """,
        (user_id,),
    )
    preview = [
        {
            "date": str(r[0]),
            "merchant": r[1],
            "amount": float(r[2] or 0),
            "type": r[3],
            "category": r[4],
        }
        for r in cur.fetchall()
    ]

    cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id = %s", (user_id,))
    total_txns = int(cur.fetchone()[0] or 0)

    return {
        "success": True,
        "bank_slug": slug,
        "bank_name": bank_label,
        "account_holder": display_name,
        "display_name": display_name,
        "transactions_linked": linked,
        "transactions_rebranded": rebranded,
        "total_transactions": total_txns,
        "already_linked": bool(existing_link) and linked == 0,
        "statement_year": sy,
        "statement_month": sm,
        "preview": preview,
        "workspace": workspace_stats,
        "message": f"Your {bank_label} account is linked, {display_name}.",
    }
