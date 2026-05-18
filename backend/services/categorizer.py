"""Merchant-based auto-categorization and UI bucket normalization."""

from __future__ import annotations

# Filter chips on the Transactions page (must stay in sync with frontend).
UI_CATEGORY_BUCKETS: tuple[str, ...] = (
    "Food & Dining",
    "Entertainment",
    "Shopping",
    "Travel",
    "Bills",
    "Other",
)

MERCHANT_CATEGORY_MAP: dict[str, str] = {
    "swiggy": "Food & Dining",
    "zomato": "Food & Dining",
    "blinkit": "Food & Dining",
    "bigbasket": "Food & Dining",
    "zepto": "Food & Dining",
    "mcdonald": "Food & Dining",
    "domino": "Food & Dining",
    "starbucks": "Food & Dining",
    "instamart": "Food & Dining",
    "dmart": "Food & Dining",
    "haldiram": "Food & Dining",
    "dunzo": "Food & Dining",
    "reliance smart": "Food & Dining",
    "mtr": "Food & Dining",
    "chai point": "Food & Dining",
    "chaipoint": "Food & Dining",
    "uber": "Transportation",
    "ola": "Transportation",
    "rapido": "Transportation",
    "indigo": "Transportation",
    "makemytrip": "Transportation",
    "redbus": "Transportation",
    "bmtc": "Transportation",
    "metro": "Transportation",
    "metro rail": "Transportation",
    "namma metro": "Transportation",
    "irctc": "Transportation",
    "punemetro": "Transportation",
    "amazon": "Shopping",
    "flipkart": "Shopping",
    "myntra": "Shopping",
    "ajio": "Shopping",
    "nykaa": "Shopping",
    "croma": "Shopping",
    "meesho": "Shopping",
    "boat": "Shopping",
    "jio": "Bills & Utilities",
    "airtel": "Bills & Utilities",
    "bescom": "Bills & Utilities",
    "tata power": "Bills & Utilities",
    "bsnl": "Bills & Utilities",
    "phonepe": "Bills & Utilities",
    "netflix": "Entertainment",
    "spotify": "Entertainment",
    "bookmyshow": "Entertainment",
    "pvr": "Entertainment",
    "hotstar": "Entertainment",
    "prime video": "Entertainment",
    "gaming": "Entertainment",
    "apollo": "Healthcare",
    "medplus": "Healthcare",
    "practo": "Healthcare",
    "1mg": "Healthcare",
    "netmeds": "Healthcare",
    "zerodha": "Finance & Investment",
    "groww": "Finance & Investment",
    "sip groww": "Finance & Investment",
    "msedcl": "Bills & Utilities",
    "mseb": "Bills & Utilities",
    "electric": "Bills & Utilities",
    "payroll": "Transfer",
    "salary": "Transfer",
    "reimbursement": "Transfer",
    "interest credit": "Finance & Investment",
    "meta ads": "Shopping",
    "intl pos": "Shopping",
    "apple.com": "Entertainment",
    "micro auth": "Entertainment",
    "lic": "Finance & Investment",
    "cred": "Finance & Investment",
    "upstox": "Finance & Investment",
    "crypto": "Finance & Investment",
    "paytm": "Transfer",
    "google pay": "Transfer",
    "bhim": "Transfer",
    "quickloan": "Transfer",
    "quickcash": "Transfer",
}

# Lowercase DB / seed / simulator labels → UI bucket (Transactions filter chips).
_CATEGORY_BUCKET_ALIASES: dict[str, tuple[str, ...]] = {
    "Food & Dining": (
        "food & dining",
        "food",
        "groceries",
        "grocery",
        "food_delivery",
        "food delivery",
        "cafe",
        "quick commerce",
        "dining",
        "restaurant",
    ),
    "Entertainment": (
        "entertainment",
        "gaming",
        "movies",
        "movie",
    ),
    "Shopping": (
        "shopping",
        "fashion",
        "electronics",
        "tech",
    ),
    "Travel": (
        "transportation",
        "transport",
        "travel",
        "petrol",
        "fuel",
    ),
    "Bills": (
        "bills & utilities",
        "utilities",
        "recharge",
        "subscription",
        "bills",
        "emi",
        "rent",
        "bill_payment",
    ),
    "Other": (
        "other",
        "others",
        "healthcare",
        "health",
        "medical",
        "finance & investment",
        "finance",
        "investment",
        "transfer",
        "salary",
        "reimbursement",
        "advertising",
        "interest",
        "cash withdrawal",
        "uncategorized",
    ),
}

# Canonical stored labels (from categorize_merchant) → UI bucket.
_STORED_TO_UI: dict[str, str] = {
    "Transportation": "Travel",
    "Bills & Utilities": "Bills",
    "Others": "Other",
    "Healthcare": "Other",
    "Finance & Investment": "Other",
    "Finance": "Other",
    "Transfer": "Other",
    "Salary": "Other",
}

_ALIAS_TO_UI: dict[str, str] = {}
for _bucket, _aliases in _CATEGORY_BUCKET_ALIASES.items():
    _ALIAS_TO_UI[_bucket.lower()] = _bucket
    for _a in _aliases:
        _ALIAS_TO_UI[_a] = _bucket


def categorize_merchant(merchant: str) -> str:
    if not merchant or not str(merchant).strip():
        return "Other"
    m = str(merchant).lower().strip()
    for key, category in MERCHANT_CATEGORY_MAP.items():
        if key in m:
            return category
    return "Other"


def normalize_category(raw: str | None) -> str:
    """Map any stored category string to a Transactions UI bucket label."""
    key = (raw or "").strip()
    if not key:
        return "Other"
    low = key.lower()
    if low in _ALIAS_TO_UI:
        return _ALIAS_TO_UI[low]
    if key in _STORED_TO_UI:
        return _STORED_TO_UI[key]
    if key in UI_CATEGORY_BUCKETS:
        return key
    # Partial match for compound labels (e.g. "Food Delivery")
    for alias, bucket in _ALIAS_TO_UI.items():
        if len(alias) >= 4 and (alias in low or low in alias):
            return bucket
    return "Other"


def resolve_category(merchant: str, raw_category: str | None = None) -> str:
    """Best category for a row: global enrich map, then legacy aliases."""
    from services.parser_utils import stored_category_for_merchant

    return stored_category_for_merchant(merchant, raw_category)


def category_filter_sql(bucket: str, alias: str = "t") -> tuple[str, list]:
    """SQL fragment matching all aliases for a UI filter chip (case-insensitive)."""
    key = (bucket or "").strip()
    if not key or key == "All":
        return "", []
    ui = normalize_category(key) if key not in UI_CATEGORY_BUCKETS else key
    if ui not in _CATEGORY_BUCKET_ALIASES:
        col = f"LOWER(TRIM(COALESCE({alias}.category, '')))"
        return f" AND {col} = %s", [key.lower()]
    aliases = list(_CATEGORY_BUCKET_ALIASES[ui])
    placeholders = ", ".join(["%s"] * len(aliases))
    col = f"LOWER(TRIM(COALESCE({alias}.category, '')))"
    return f" AND {col} IN ({placeholders})", aliases


def categorize_batch(merchants: list[str]) -> list[str]:
    return [categorize_merchant(m) for m in merchants]
