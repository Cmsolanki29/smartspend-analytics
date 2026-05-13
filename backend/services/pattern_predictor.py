"""Predict upcoming subscription / dark-pattern charges from real transaction history."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from psycopg2.extensions import connection as PgConnection


def _to_dt(d: date, t: Any) -> datetime:
    if isinstance(t, datetime):
        return t
    return datetime.combine(d, t)


def _fetch_txns(conn: PgConnection, user_id: int, months: int = 6) -> list[dict[str, Any]]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, transaction_date, transaction_time, amount::float, COALESCE(type, ''),
                   COALESCE(merchant, ''), COALESCE(description, '')
            FROM transactions
            WHERE user_id = %s
              AND transaction_date >= (CURRENT_DATE - %s::interval)
            ORDER BY transaction_date ASC, transaction_time ASC;
            """,
            (user_id, f"{int(months)} months"),
        )
        rows = cur.fetchall()
    finally:
        cur.close()

    out: list[dict[str, Any]] = []
    for rid, d, tm, amt, tx_type, merchant, desc in rows:
        out.append(
            {
                "id": int(rid),
                "date": d,
                "time": tm,
                "dt": _to_dt(d, tm),
                "amount": float(amt or 0),
                "type": (tx_type or "").strip(),
                "merchant": (merchant or "").strip(),
                "description": (desc or "").strip(),
            }
        )
    return out


def _trial_merchant(merchant: str) -> bool:
    low = merchant.lower()
    return any(k in low for k in ("cloud", "vpn", "secure", "trial", "pro", "app", "fit", "plus"))


def predict_upcoming_charges(conn: PgConnection, user_id: int) -> list[dict[str, Any]]:
    """Return alert dicts ready for INSERT into pattern_alerts."""
    today = date.today()
    now = datetime.now()
    txns = _fetch_txns(conn, user_id, months=8)
    alerts: list[dict[str, Any]] = []

    debits = [t for t in txns if t["type"] == "DEBIT" and t["merchant"]]
    by_merchant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in debits:
        by_merchant[t["merchant"]].append(t)
    for m in by_merchant:
        by_merchant[m].sort(key=lambda x: x["dt"])

    # --- Free trial ending (small charge, follow-up large known OR predicted window) ---
    for merchant, items in by_merchant.items():
        if not _trial_merchant(merchant):
            continue
        for i, tx in enumerate(items):
            if tx["amount"] > 10:
                continue
            if tx["amount"] < 0.5:
                continue
            # Look for large follow-up same merchant after this tx
            follow = None
            for nxt in items[i + 1 :]:
                if nxt["amount"] >= 99 and (nxt["date"] - tx["date"]).days >= 3:
                    follow = nxt
                    break
            if follow:
                # Upcoming renewal: next cycle ~ same gap after follow
                gap = (follow["date"] - tx["date"]).days
                gap = max(7, min(gap, 90))
                next_charge = follow["date"] + timedelta(days=gap)
                if next_charge > today:
                    alerts.append(
                        _alert_row(
                            user_id,
                            "free_trial_ending",
                            merchant,
                            float(follow["amount"]),
                            next_charge,
                            follow["id"],
                            0.82,
                            {"trial_anchor": tx["date"].isoformat(), "last_paid": follow["date"].isoformat()},
                        )
                    )
            else:
                # No follow-up yet — predict common trial lengths from small charge date
                for days in (7, 14, 30):
                    end = tx["date"] + timedelta(days=days)
                    if end > today:
                        est = _estimate_avg_debit(conn, user_id, merchant) or 499.0
                        alerts.append(
                            _alert_row(
                                user_id,
                                "free_trial_ending",
                                merchant,
                                float(est),
                                end,
                                tx["id"],
                                0.65,
                                {"trial_start": tx["date"].isoformat(), "assumed_days": days},
                            )
                        )
                        break

    # --- Monthly renewal (same amount, ~28–32 day gaps) ---
    for merchant, items in by_merchant.items():
        if len(items) < 2:
            continue
        amounts = [round(x["amount"], 2) for x in items if x["amount"] >= 49]
        if len(amounts) < 2:
            continue
        last_amt = amounts[-1]
        same = [x for x in items if x["type"] == "DEBIT" and round(x["amount"], 2) == last_amt]
        if len(same) < 2:
            continue
        dates = [x["date"] for x in same]
        intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        if not intervals:
            continue
        if all(26 <= iv <= 35 for iv in intervals):
            last_d = dates[-1]
            next_d = last_d + timedelta(days=30)
            if next_d > today:
                alerts.append(
                    _alert_row(
                        user_id,
                        "renewal_upcoming",
                        merchant,
                        float(last_amt),
                        next_d,
                        same[-1]["id"],
                        0.9,
                        {"frequency": "monthly", "history_count": len(same)},
                    )
                )

    # --- One-rupee trap predicted ---
    for merchant, items in by_merchant.items():
        for tx in items:
            if tx["amount"] > 1.0:
                continue
            if tx["type"] != "DEBIT":
                continue
            large_later = any(
                y["merchant"] == merchant and y["amount"] > 100 and y["date"] > tx["date"] for y in items
            )
            if large_later:
                continue
            pred = tx["date"] + timedelta(days=7)
            if pred > today:
                alerts.append(
                    _alert_row(
                        user_id,
                        "one_rupee_trap_predicted",
                        merchant,
                        499.0,
                        pred,
                        tx["id"],
                        0.55,
                        {"verification_date": tx["date"].isoformat(), "verification_amount": tx["amount"]},
                    )
                )
                break

    # --- Price increase (reactive heads-up, optional next bill at new price) ---
    for merchant, items in by_merchant.items():
        if len(items) < 2:
            continue
        deb = [x for x in items if x["amount"] >= 10]
        if len(deb) < 2:
            continue
        a, b = deb[-2], deb[-1]
        if b["amount"] > a["amount"] * 1.1 and b["date"] >= today - timedelta(days=45):
            inc_pct = (b["amount"] - a["amount"]) / max(a["amount"], 1) * 100
            if inc_pct > 10:
                alerts.append(
                    _alert_row(
                        user_id,
                        "price_increase",
                        merchant,
                        float(b["amount"]),
                        b["date"],
                        b["id"],
                        0.95,
                        {
                            "old_price": float(a["amount"]),
                            "new_price": float(b["amount"]),
                            "increase_pct": round(inc_pct, 1),
                        },
                    )
                )

    # Dedupe by (merchant, charge_date, pattern_type) keeping highest confidence
    keyed: dict[tuple[str, date, str], dict[str, Any]] = {}
    for a in alerts:
        k = (a["merchant_name"], a["charge_date"], a["pattern_type"])
        if k not in keyed or (a["predicted_confidence"] or 0) > (keyed[k].get("predicted_confidence") or 0):
            keyed[k] = a
    return sorted(keyed.values(), key=lambda x: (x["charge_date"], -float(x["predicted_confidence"] or 0)))


def _alert_row(
    user_id: int,
    pattern_type: str,
    merchant: str,
    charge_amount: float,
    charge_date: date,
    source_txn_id: int | None,
    confidence: float,
    details: dict[str, Any],
) -> dict[str, Any]:
    """Build one alert payload matching pattern_alerts columns."""
    first = charge_date - timedelta(days=3)
    if pattern_type == "renewal_upcoming" and charge_date - date.today() > timedelta(days=20):
        first = charge_date - timedelta(days=3)
    deadline = datetime.combine(charge_date, datetime.min.time()) - timedelta(hours=12)
    return {
        "user_id": user_id,
        "pattern_type": pattern_type,
        "merchant_name": merchant[:250],
        "charge_amount": round(charge_amount, 2),
        "charge_date": charge_date,
        "action_deadline": deadline,
        "first_alert_date": first,
        "source_transaction_id": source_txn_id,
        "predicted_confidence": round(min(0.99, max(0.05, confidence)), 2),
        "details_json": details,
    }


def _estimate_avg_debit(conn: PgConnection, user_id: int, merchant: str) -> float | None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT AVG(amount)::float FROM transactions
            WHERE user_id = %s AND type = 'DEBIT' AND merchant = %s AND amount > 15;
            """,
            (user_id, merchant),
        )
        r = cur.fetchone()
        return float(r[0]) if r and r[0] is not None else None
    finally:
        cur.close()


def upsert_pattern_alerts(conn: PgConnection, alerts: list[dict[str, Any]]) -> int:
    """Insert new pattern_alerts; skip duplicates. Returns rows inserted."""
    if not alerts:
        return 0
    cur = conn.cursor()
    n = 0
    try:
        for a in alerts:
            cur.execute(
                """
                INSERT INTO pattern_alerts (
                  user_id, pattern_type, merchant_name, charge_amount, charge_date,
                  action_deadline, first_alert_date, source_transaction_id,
                  predicted_confidence, details_json, status, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, 'pending', NOW())
                ON CONFLICT (user_id, pattern_type, merchant_name, charge_date) DO NOTHING
                RETURNING id;
                """,
                (
                    a["user_id"],
                    a["pattern_type"],
                    a["merchant_name"],
                    a["charge_amount"],
                    a["charge_date"],
                    a["action_deadline"],
                    a["first_alert_date"],
                    a.get("source_transaction_id"),
                    a.get("predicted_confidence"),
                    json.dumps(a.get("details_json") or {}),
                ),
            )
            if cur.fetchone():
                n += 1
    finally:
        cur.close()
    return n


def expire_stale_alerts(conn: PgConnection, user_id: int | None = None) -> int:
    cur = conn.cursor()
    try:
        if user_id is not None:
            cur.execute(
                """
                UPDATE pattern_alerts SET status = 'expired', updated_at = NOW()
                WHERE user_id = %s AND status IN ('pending', 'snoozed')
                  AND charge_date < CURRENT_DATE;
                """,
                (user_id,),
            )
        else:
            cur.execute(
                """
                UPDATE pattern_alerts SET status = 'expired', updated_at = NOW()
                WHERE status IN ('pending', 'snoozed') AND charge_date < CURRENT_DATE;
                """
            )
        return cur.rowcount or 0
    finally:
        cur.close()
