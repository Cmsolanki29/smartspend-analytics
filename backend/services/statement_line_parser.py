"""
Deterministic parsers for Indian bank/CC statement text (Axis-style tables).

Used when PDF text matches ``DD-Mon narration amount`` rows — avoids LLM misses.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from services.parser_utils import stored_category_for_merchant

_MONTH_ABBR = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_CREDIT_HINTS = (
    "neft cr",
    "upi from",
    "reimbursement",
    "interest credit",
    "salary",
    "payroll",
    "credit interest",
    "int.pd",
)

_LINE_RE = re.compile(
    r"^(\d{1,2})-([A-Za-z]{3})\s+(.+?)\s+(\d+(?:\.\d{1,2})?)\s*$",
    re.IGNORECASE,
)

_PERIOD_RE = re.compile(
    r"statement\s+period\s*:\s*\d{1,2}\s+([A-Za-z]+)\s+(\d{4})",
    re.IGNORECASE,
)


def _statement_year_month(text: str) -> tuple[int, int]:
    m = _PERIOD_RE.search(text or "")
    if m:
        mon_name = m.group(1).lower()[:3]
        year = int(m.group(2))
        month = _MONTH_ABBR.get(mon_name, 5)
        return year, month
    return date.today().year, date.today().month


def _infer_type(narration: str) -> str:
    low = narration.lower()
    if any(h in low for h in _CREDIT_HINTS):
        return "credit"
    return "debit"


def parse_axis_style_statement(text: str) -> list[dict[str, Any]]:
    """
    Parse lines like ``05-May MSEDCL BILL AUTOPAY 1860`` from Axis sample statements.
    Returns monster-compatible dicts: date, description, amount, type, category.
    """
    if not text:
        return []

    year, default_month = _statement_year_month(text)
    out: list[dict[str, Any]] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        day_s, mon_abbr, narration, amt_s = m.groups()
        mon = _MONTH_ABBR.get(mon_abbr.lower()[:3])
        if not mon:
            mon = default_month
        try:
            d = date(year, mon, int(day_s))
        except ValueError:
            continue
        try:
            amount = float(amt_s)
        except ValueError:
            continue
        if amount <= 0:
            continue
        narr = narration.strip()
        txn_type = _infer_type(narr)
        category = stored_category_for_merchant(narr, None)
        out.append(
            {
                "date": d.isoformat(),
                "description": narr,
                "amount": amount,
                "type": txn_type,
                "category": category,
            }
        )
    # Require table header OR enough DD-Mon rows (pdfplumber sometimes drops headers).
    if not out:
        return []
    if "date narration" not in text.lower() and len(out) < 8:
        return []
    return out


# DD-MM-YYYY / DD/MM/YY rows (HDFC, ICICI, Axis, Kotak, most Indian bank PDFs)
_NUMERIC_DATE_LINE = re.compile(
    r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\s+(.+)$",
)
_AMOUNT_TAIL = re.compile(r"([\d,]+\.\d{2})\s*$")
_SKIP_LINE = re.compile(
    r"^(date|txn\s*date|tran\s*date|narration|particulars|description|withdrawal|deposit|debit|credit|balance|closing|statement|account\s+holder|branch|period|transaction\s+details)",
    re.I,
)


def _parse_numeric_date(day_s: str, mon_s: str, year_s: str) -> date | None:
    try:
        day, month = int(day_s), int(mon_s)
        year = int(year_s)
        if year < 100:
            year += 2000 if year < 70 else 1900
        return date(year, month, day)
    except ValueError:
        return None


def _repair_running_balance_rows(
    parsed: list[dict[str, Any]],
    text: str,
) -> list[dict[str, Any]]:
    from services.upload_amount_sanity import repair_running_balance_transactions

    return repair_running_balance_transactions(parsed, text=text)


def parse_indian_tabular_statement(text: str) -> list[dict[str, Any]]:
    """
    Parse statement text with numeric dates (``01-02-2026``, ``15/03/24``).
    Works for PDF text from any bank when table rows survive extraction.
    """
    if not text or len(text) < 80:
        return []

    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip().replace("|", " ")
        line = re.sub(r"\s+", " ", line)
        if not line or len(line) < 12:
            continue
        if _SKIP_LINE.match(line):
            continue
        m = _NUMERIC_DATE_LINE.match(line)
        if not m:
            continue
        day_s, mon_s, year_s, rest = m.groups()
        txn_date = _parse_numeric_date(day_s, mon_s, year_s)
        if not txn_date:
            continue

        amounts = [float(a.replace(",", "")) for a in _AMOUNT_TAIL.findall(rest)]
        if not amounts:
            # narration may end with amount only (no balance column)
            all_amts = re.findall(r"([\d,]+\.\d{2})", rest)
            if not all_amts:
                continue
            amounts = [float(all_amts[-1].replace(",", ""))]

        narration = rest
        for a in re.findall(r"[\d,]+\.\d{2}", rest):
            narration = narration.replace(a, " ")
        narration = re.sub(r"\s+", " ", narration).strip() or "Transaction"

        if len(amounts) >= 3:
            withdrawal, deposit, _balance = amounts[0], amounts[1], amounts[2]
            if withdrawal > 0 and deposit <= 0:
                amount, txn_type = withdrawal, "debit"
            elif deposit > 0 and withdrawal <= 0:
                amount, txn_type = deposit, "credit"
            elif deposit >= withdrawal:
                amount, txn_type = deposit, "credit"
            else:
                amount, txn_type = withdrawal, "debit"
        elif len(amounts) == 2:
            first, second = amounts[0], amounts[1]
            # Often: txn amount + running balance (second value larger)
            if second > first * 1.5 and first > 0:
                amount = first
                txn_type = _infer_type(narration)
            elif first > 0 and second <= 0:
                amount, txn_type = first, "debit"
            elif second > 0 and first <= 0:
                amount, txn_type = second, "credit"
            else:
                amount = first
                txn_type = _infer_type(narration)
        else:
            # Single trailing number — usually closing balance when W/D columns missing in PDF text.
            amount = amounts[0]
            txn_type = _infer_type(narration)

        if amount <= 0:
            continue
        out.append(
            {
                "date": txn_date.isoformat(),
                "description": narration[:200],
                "amount": amount,
                "type": txn_type,
                "category": stored_category_for_merchant(narration, None),
            }
        )

    if len(out) < 5:
        return []
    return _repair_running_balance_rows(out, text)


def parse_transactions_from_extraction_tables(tables: list | None) -> list[dict[str, Any]]:
    """Turn pdfplumber table grids or bank_parser row lists into upload txn dicts."""
    if not tables:
        return []

    first = tables[0]
    if isinstance(first, list) and first and isinstance(first[0], dict):
        if first[0].get("transaction_date") or first[0].get("amount"):
            return _bank_parser_rows_to_monster(first)

    try:
        import pandas as pd
        from services.bank_parser import BankStatementParser

        parser = BankStatementParser()
        for table in tables:
            if not table or not isinstance(table, list):
                continue
            if not isinstance(table[0], (list, tuple)):
                continue
            rows = [[str(c or "").strip() for c in row] for row in table if row]
            if len(rows) < 2:
                continue
            header = [h.lower() for h in rows[0]]
            if not any(k in " ".join(header) for k in ("date", "narration", "particular", "debit", "withdrawal")):
                continue
            df = pd.DataFrame(rows[1:], columns=rows[0])
            bank_txns = parser.parse_dataframe(df)
            if bank_txns:
                return _bank_parser_rows_to_monster(bank_txns)
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning("table bank parse skipped: %s", exc)
    return []


def _bank_parser_rows_to_monster(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        d = row.get("transaction_date") or row.get("date")
        if hasattr(d, "isoformat"):
            date_str = d.isoformat()
        else:
            date_str = str(d)[:10] if d else ""
        if not date_str:
            continue
        try:
            amount = float(row.get("amount", 0))
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        raw_type = str(row.get("type", "DEBIT")).upper()
        txn_type = "credit" if raw_type == "CREDIT" else "debit"
        desc = str(row.get("description") or row.get("merchant") or "Transaction")[:200]
        out.append(
            {
                "date": date_str,
                "description": desc,
                "amount": amount,
                "type": txn_type,
                "category": row.get("category"),
            }
        )
    return out


def best_deterministic_transactions(
    text: str,
    tables: list | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Pick the best non-LLM parse — prefer structured table columns over PDF text lines."""
    candidates: list[tuple[str, list[dict[str, Any]]]] = []
    for name, fn in (
        ("pdf_tables", lambda: parse_transactions_from_extraction_tables(tables)),
        ("indian_tabular", lambda: parse_indian_tabular_statement(text)),
        ("axis_line", lambda: parse_axis_style_statement(text)),
    ):
        try:
            rows = fn()
            if len(rows) >= 5:
                candidates.append((name, rows))
        except Exception:  # noqa: BLE001
            continue
    if not candidates:
        return [], "none"

    from services.upload_amount_sanity import amounts_look_like_running_balances

    by_name = {name: rows for name, rows in candidates}
    table_rows = by_name.get("pdf_tables") or []
    line_rows = by_name.get("indian_tabular") or by_name.get("axis_line") or []

    if table_rows and not amounts_look_like_running_balances(table_rows):
        return table_rows, "pdf_tables"
    if table_rows and line_rows and amounts_look_like_running_balances(line_rows):
        if not amounts_look_like_running_balances(table_rows):
            return table_rows, "pdf_tables"

    sane = [(n, r) for n, r in candidates if not amounts_look_like_running_balances(r)]
    pool = sane if sane else candidates
    best_name, best_rows = max(pool, key=lambda x: len(x[1]))
    return best_rows, best_name
