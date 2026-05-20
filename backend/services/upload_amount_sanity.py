"""
Upload amount sanity — prevent closing-balance-as-amount from reaching the dashboard.

Used for every bank PDF/CSV/credit-card ingest (judge demos + real users).
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Single transaction above this (INR) is almost always a parse bug for retail banking.
MAX_SINGLE_TXN_INR = 2_000_000.0
# Median debit above this with huge max ⇒ likely balance column stored as amount.
BALANCE_LIKE_MEDIAN_DEBIT = 80_000.0
BALANCE_LIKE_MAX_RATIO = 40.0


def amounts_look_like_running_balances(rows: list[dict[str, Any]]) -> bool:
    if len(rows) < 8:
        return False
    amts = [float(r.get("amount") or 0) for r in rows[:80]]
    if not amts:
        return False
    big = sum(1 for a in amts if a >= BALANCE_LIKE_MEDIAN_DEBIT)
    if big >= max(6, len(amts) // 2):
        return True
    med = sorted(amts)[len(amts) // 2]
    mx = max(amts)
    return mx >= BALANCE_LIKE_MEDIAN_DEBIT and med > 0 and (mx / med) >= BALANCE_LIKE_MAX_RATIO


def _parse_opening_balance(text: str) -> float | None:
    for pat in (
        r"opening\s+balance[:\s]*([\d,]+\.?\d*)",
        r"balance\s+brought\s+forward[:\s]*([\d,]+\.?\d*)",
        r"opening\s+bal[:\s]*([\d,]+\.?\d*)",
    ):
        m = re.search(pat, text or "", re.I)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def _infer_opening_balance(
    ordered: list[dict[str, Any]],
    text: str,
    monthly_income: float | None,
) -> float | None:
    opening = _parse_opening_balance(text)
    if opening is not None and opening > 0:
        return opening
    if not ordered:
        return None
    first = ordered[0]
    bal0 = float(first.get("amount") or 0)
    desc0 = str(first.get("description") or "").upper()
    if monthly_income and monthly_income > 0 and "SALARY" in desc0 and bal0 > monthly_income:
        return round(bal0 - monthly_income, 2)
    return None


def repair_running_balance_transactions(
    rows: list[dict[str, Any]],
    *,
    text: str = "",
    monthly_income: float | None = None,
) -> list[dict[str, Any]]:
    """Convert balance-after values into true debit/credit amounts (chronological deltas)."""
    if not rows or not amounts_look_like_running_balances(rows):
        return rows

    ordered = sorted(rows, key=lambda r: (r.get("date") or "", r.get("description") or ""))
    opening = _infer_opening_balance(ordered, text, monthly_income)
    out: list[dict[str, Any]] = []
    prev = opening

    for row in ordered:
        bal = float(row.get("amount") or 0)
        if bal <= 0:
            continue
        if prev is None:
            desc = str(row.get("description") or "").upper()
            if opening is not None:
                if bal >= opening:
                    amt, txn_type = round(bal - opening, 2), "credit"
                else:
                    amt, txn_type = round(opening - bal, 2), "debit"
                if amt > 0:
                    out.append({**row, "amount": amt, "type": txn_type})
            elif monthly_income and monthly_income > 0 and "SALARY" in desc:
                out.append({**row, "amount": round(monthly_income, 2), "type": "credit"})
            prev = bal
            continue

        if bal >= prev:
            amt, txn_type = round(bal - prev, 2), "credit"
        else:
            amt, txn_type = round(prev - bal, 2), "debit"
        if amt <= 0:
            prev = bal
            continue
        if amt > MAX_SINGLE_TXN_INR:
            prev = bal
            continue
        out.append({**row, "amount": amt, "type": txn_type})
        prev = bal

    return out if len(out) >= max(5, len(rows) // 4) else rows


def _fetch_monthly_income(cur, user_id: int) -> float | None:
    try:
        cur.execute(
            "SELECT COALESCE(monthly_income, 0)::float FROM users WHERE id = %s;",
            (user_id,),
        )
        row = cur.fetchone()
        if row and float(row[0] or 0) > 0:
            return float(row[0])
    except Exception:  # noqa: BLE001
        pass
    return None


def _cap_insane_amounts(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Drop rows that are still implausible after repair."""
    kept: list[dict[str, Any]] = []
    dropped = 0
    for row in rows:
        try:
            amt = float(row.get("amount") or 0)
        except (TypeError, ValueError):
            dropped += 1
            continue
        if amt <= 0 or amt > MAX_SINGLE_TXN_INR:
            dropped += 1
            continue
        kept.append(row)
    return kept, dropped


def sanitize_transactions_before_import(
    transactions: list[dict[str, Any]],
    *,
    text: str = "",
    tables: list | None = None,
    conn=None,
    user_id: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Normalize parsed upload rows before DB insert.
    Prefer bank_parser table rows when line-parse looks like balances.
    """
    meta: dict[str, Any] = {
        "repaired_running_balance": False,
        "preferred_table_parse": False,
        "dropped_insane_rows": 0,
        "warnings": [],
    }
    if not transactions:
        return transactions, meta

    monthly_income = None
    if conn is not None and user_id is not None:
        cur = conn.cursor()
        try:
            monthly_income = _fetch_monthly_income(cur, user_id)
        finally:
            cur.close()

    # If we have structured bank_parser rows in tables, prefer them over broken line parse.
    if amounts_look_like_running_balances(transactions) and tables:
        try:
            from services.statement_line_parser import parse_transactions_from_extraction_tables

            table_rows = parse_transactions_from_extraction_tables(tables)
            if table_rows and not amounts_look_like_running_balances(table_rows):
                transactions = table_rows
                meta["preferred_table_parse"] = True
                meta["warnings"].append("Switched to table/bank_parser columns (withdrawal/deposit).")
        except Exception as exc:  # noqa: BLE001
            logger.warning("table re-parse skipped: %s", exc)

    if amounts_look_like_running_balances(transactions):
        repaired = repair_running_balance_transactions(
            transactions,
            text=text,
            monthly_income=monthly_income,
        )
        if repaired is not transactions and not amounts_look_like_running_balances(repaired):
            transactions = repaired
            meta["repaired_running_balance"] = True
            meta["warnings"].append(
                "Corrected PDF amounts from closing-balance column to true debit/credit."
            )
        elif repaired is not transactions:
            meta["warnings"].append("Attempted running-balance repair; review statement format.")

    transactions, dropped = _cap_insane_amounts(transactions)
    meta["dropped_insane_rows"] = dropped
    if dropped:
        meta["warnings"].append(f"Dropped {dropped} rows with implausible amounts.")

    return transactions, meta


def user_ledger_looks_corrupted(cur, user_id: int) -> bool:
    """True when stored amounts look like running balances (dashboard would panic)."""
    cur.execute(
        """
        SELECT amount::float, type
        FROM transactions
        WHERE user_id = %s
        ORDER BY transaction_date ASC, id ASC
        LIMIT 120;
        """,
        (user_id,),
    )
    rows = [{"amount": float(r[0]), "type": r[1]} for r in cur.fetchall()]
    return amounts_look_like_running_balances(rows)


def repair_user_ledger_from_balances(
    conn,
    user_id: int,
    *,
    opening_hint: float | None = 118_000.0,
) -> int:
    """
    Post-import safety net: recompute amounts for all user txns when corruption detected.
    Returns number of rows updated.
    """
    cur = conn.cursor()
    try:
        if not user_ledger_looks_corrupted(cur, user_id):
            return 0
        monthly_income = _fetch_monthly_income(cur, user_id)
        cur.execute(
            """
            SELECT id, transaction_date, type, amount::float, description
            FROM transactions
            WHERE user_id = %s
            ORDER BY transaction_date ASC, id ASC;
            """,
            (user_id,),
        )
        raw = cur.fetchall()
        if not raw:
            return 0

        opening = opening_hint
        if monthly_income and raw:
            first_desc = str(raw[0][4] or "").upper()
            if "SALARY" in first_desc:
                opening = float(raw[0][3]) - monthly_income

        prev = opening
        updated = 0
        for tid, _d, _typ, bal, _desc in raw:
            bal = float(bal)
            if prev is None:
                prev = bal
                continue
            if bal >= prev:
                true_amt, true_type = round(bal - prev, 2), "CREDIT"
            else:
                true_amt, true_type = round(prev - bal, 2), "DEBIT"
            if 0 < true_amt <= MAX_SINGLE_TXN_INR:
                cur.execute(
                    "UPDATE transactions SET amount = %s, type = %s WHERE id = %s AND user_id = %s;",
                    (true_amt, true_type, tid, user_id),
                )
                updated += 1
            prev = bal
        conn.commit()
        return updated
    finally:
        cur.close()


def verify_user_ledger_after_import(conn, user_id: int) -> dict[str, Any]:
    """Run after every upload; repair + resync summaries if corruption detected."""
    from services.transaction_enrichment import sync_all_monthly_summaries_for_user

    out: dict[str, Any] = {"repaired_rows": 0, "months_synced": 0}
    try:
        repaired = repair_user_ledger_from_balances(conn, user_id)
        out["repaired_rows"] = repaired
        if repaired > 0:
            out["months_synced"] = sync_all_monthly_summaries_for_user(conn, user_id)
            conn.commit()
            logger.warning(
                "upload_amount_sanity: repaired user_id=%s rows=%s months=%s",
                user_id,
                repaired,
                out["months_synced"],
            )
    except Exception:  # noqa: BLE001
        logger.exception("verify_user_ledger_after_import failed user_id=%s", user_id)
    return out
