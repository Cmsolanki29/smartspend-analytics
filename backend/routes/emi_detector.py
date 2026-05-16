"""EMI Tracker analysis routes — recurring loan detection and safe-capacity checks."""

from __future__ import annotations

import calendar
import math
import statistics
from collections import defaultdict
from datetime import date, datetime
from statistics import median
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_db
from services.dashboard_scope import fetch_dashboard_mode, transaction_scope_sql
from services.openai_service import call_gpt

router = APIRouter(prefix="/emi", tags=["EMI Tracker"])

SUBSCRIPTION_SKIP = ("netflix", "spotify", "zee", "linkedin", "hotstar", "prime video", "youtube premium")
MERCHANT_FINANCE_HINTS = (
    "emi",
    "loan",
    "finserv",
    "capital",
    "housing",
    "financial",
    "hdfc",
    "icici",
    "sbi",
    "axis",
    "kotak",
    "bajaj",
    "mahindra",
    "ltfs",
    "mortgage",
    "home loan",
    "personal",
    "nach",
    "ecs",
    "nbfc",
    "lending",
    "equated",
    "installment",
    "repayment",
    "hl ",
    "pl ",
)


def _emi_group_key(merchant: str, description: str, amount: float) -> str:
    """Split same-merchant rows when narration or amount clearly indicates separate EMIs."""
    m = (merchant or "").strip()
    d = (description or "").strip().lower()
    if any(k in d for k in ("emi", "loan", "installment", "nach", "ecs", "auto debit", "repayment")):
        return f"{m}|{d[:80]}"
    return f"{m}|{round(float(amount or 0))}"


def _source_label(institution: str, source_type: str) -> str:
    inst = (institution or "").strip() or "Unknown source"
    st = (source_type or "").strip().lower()
    if st == "credit_card":
        return f"{inst} (Credit Card)"
    if st in ("bank", "bank_statement_pdf"):
        return f"{inst} (Bank)"
    if st:
        return f"{inst} ({st.replace('_', ' ')})"
    return inst


def _append_card_statement_burden(
    cur,
    user_id: int,
    mode: str,
    emi_entries: list[dict[str, Any]],
) -> None:
    """When card sources are in scope, surface monthly card spend as a debt line item."""
    if mode not in ("credit_card_only", "merged"):
        return
    scope = transaction_scope_sql("t", mode)
    cur.execute(
        f"""
        SELECT cs.institution_name, cs.source_type,
               COALESCE(SUM(t.amount), 0)::float AS month_spend
        FROM transactions t
        JOIN connected_sources cs ON cs.id = t.connected_source_id AND cs.user_id = t.user_id
        WHERE t.user_id = %s
          AND t.type = 'DEBIT'
          AND cs.source_type = 'credit_card'
          AND t.transaction_date >= DATE_TRUNC('month', CURRENT_DATE)
          AND ({scope})
        GROUP BY cs.id, cs.institution_name, cs.source_type
        HAVING COALESCE(SUM(t.amount), 0) >= 1000
        ORDER BY month_spend DESC;
        """,
        (user_id,),
    )
    existing_sources = {e.get("source_name", "").lower() for e in emi_entries}
    for institution, source_type, month_spend in cur.fetchall():
        label = _source_label(institution, source_type)
        if label.lower() in existing_sources:
            continue
        spend = float(month_spend or 0)
        if spend < 1000:
            continue
        emi_entries.append(
            {
                "merchant": f"{institution} — card spend (this month)",
                "amount": round(spend, 2),
                "payment_date": 1,
                "category": "credit_card",
                "emi_type": "CREDIT CARD",
                "months_detected": 1,
                "first_detected": date.today().replace(day=1).isoformat(),
                "last_detected": date.today().isoformat(),
                "next_due": _next_due_date(1, date.today()).isoformat(),
                "source_name": label,
                "source_type": source_type or "credit_card",
                "is_statement_burden": True,
            }
        )


def _infer_monthly_income(cur, user_id: int, mode: str = "merged") -> float:
    """When users.monthly_income is missing, estimate from recent salary-like credits."""
    scope = transaction_scope_sql("t", mode)
    cur.execute(
        f"""
        SELECT COALESCE(MAX(month_total), 0)::float
        FROM (
            SELECT SUM(t.amount) AS month_total
            FROM transactions t
            WHERE t.user_id = %s
              AND t.type = 'CREDIT'
              AND t.transaction_date >= (CURRENT_DATE - INTERVAL '9 months')
              AND ({scope})
            GROUP BY DATE_TRUNC('month', t.transaction_date)
        ) q;
        """,
        (user_id,),
    )
    row = cur.fetchone()
    mx = float(row[0] or 0)
    if mx > 0:
        return max(mx, 25000.0)
    return 52000.0


def _amounts_plausible(amounts: list[float], med: float) -> bool:
    if med < 500 or med > 500_000 or len(amounts) < 2:
        return False
    if len(amounts) == 2:
        return all(abs(a - med) / med <= 0.18 for a in amounts)
    try:
        stdev = statistics.pstdev(amounts)
        return (stdev / med) <= 0.22
    except statistics.StatisticsError:
        return all(abs(a - med) / med <= 0.15 for a in amounts)


def _dates_plausible(dates: list[date], med_day: int) -> bool:
    ok = sum(1 for d in dates if abs(d.day - med_day) <= 8)
    return ok >= max(1, int(0.45 * len(dates)))


def _month_index(d: date) -> int:
    return d.year * 12 + d.month


def _longest_consecutive_month_streak(dates: list[date]) -> tuple[int, date, date]:
    if not dates:
        return 0, date.today(), date.today()
    ordered = sorted(dates)
    unique_months = sorted({_month_index(d) for d in ordered})
    best = 1
    cur = 1
    best_end_idx = unique_months[0]
    for i in range(1, len(unique_months)):
        if unique_months[i] == unique_months[i - 1] + 1:
            cur += 1
            if cur > best:
                best = cur
                best_end_idx = unique_months[i]
        else:
            cur = 1
    best_start_idx = best_end_idx - best + 1
    start_candidates = [d for d in ordered if _month_index(d) == best_start_idx]
    end_candidates = [d for d in ordered if _month_index(d) == best_end_idx]
    return best, min(start_candidates), max(end_candidates)


def _classify_emi_type(merchant: str, category: str, amount: float, description_blob: str) -> str:
    text = f"{merchant} {description_blob}".lower()
    cat = (category or "").lower()
    if any(k in text for k in ("home", "housing", "mortgage", "lic housing")):
        return "HOME_LOAN"
    if any(k in text for k in ("car", "vehicle", "auto", "bmw")):
        return "VEHICLE EMI"
    if any(k in text for k in ("phone", "mobile", "gadget", "bajaj")):
        return "PHONE/GADGET EMI"
    if "credit card" in text or "min due" in text:
        return "CREDIT_CARD"
    if any(k in text for k in ("loan", "emi", "equated", "installment", "installment")):
        return "LOAN"
    if "finance" in cat:
        return "INVESTMENT_EMI"
    if 1000 <= amount <= 5000:
        return "PHONE/GADGET EMI"
    if 5000 < amount <= 15000:
        return "VEHICLE EMI"
    if amount > 15000:
        return "HOME_LOAN"
    return "OTHER"


def _next_due_date(payment_day: int, today: date) -> date:
    year, month = today.year, today.month
    days_in_month = calendar.monthrange(year, month)[1]
    candidate = date(year, month, min(payment_day, days_in_month))
    if candidate <= today:
        month = month + 1
        if month == 13:
            year += 1
            month = 1
        days_in_month = calendar.monthrange(year, month)[1]
        candidate = date(year, month, min(payment_day, days_in_month))
    return candidate


def _danger_from_ratio(ratio: float) -> str:
    if ratio < 20:
        return "SAFE"
    if ratio < 30:
        return "WARNING"
    if ratio <= 40:
        return "DANGER"
    return "CRITICAL"


def _build_emi_detection(conn, user_id: int) -> dict[str, Any]:
    mode = "merged"
    cur = conn.cursor()
    try:
        mode = fetch_dashboard_mode(cur, user_id)
        scope = transaction_scope_sql("t", mode)

        cur.execute(
            """
            SELECT name, monthly_income::float
            FROM users
            WHERE id = %s;
            """,
            (user_id,),
        )
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user_name, monthly_income = user[0], float(user[1] or 0)
        if monthly_income <= 0:
            monthly_income = _infer_monthly_income(cur, user_id, mode)

        cur.execute(
            f"""
            SELECT t.merchant, t.amount::float, t.transaction_date,
                   COALESCE(t.category, ''), COALESCE(t.description, ''),
                   COALESCE(cs.institution_name, ''), COALESCE(cs.source_type, '')
            FROM transactions t
            LEFT JOIN connected_sources cs
              ON cs.id = t.connected_source_id AND cs.user_id = t.user_id
            WHERE t.user_id = %s
              AND t.type = 'DEBIT'
              AND t.transaction_date >= (CURRENT_DATE - INTERVAL '6 months')
              AND t.merchant IS NOT NULL
              AND t.merchant <> ''
              AND ({scope});
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    finally:
        cur.close()

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for merchant, amount, tx_date, category, description, institution, source_type in rows:
        m = str(merchant).strip()
        amt = float(amount or 0)
        gkey = _emi_group_key(m, description or "", amt)
        grouped[gkey].append(
            {
                "amount": amt,
                "date": tx_date,
                "category": category or "",
                "description": description or "",
                "merchant": m,
                "institution": institution or "",
                "source_type": source_type or "",
            }
        )

    # Keywords that unambiguously flag a transaction as a loan/EMI repayment —
    # strong enough to detect even from a single month of bank statement data.
    _EXPLICIT_EMI_TRIGGERS = (
        "emi auto debit", "auto debit", "emi debit", "loan emi",
        "nach debit", "nach cr", "nach dr", "ecs debit",
        "car loan", "home loan", "personal loan", "vehicle loan",
        "loan repayment", "loan installment", "equated monthly",
    )

    emi_entries: list[dict[str, Any]] = []
    seen_merchants: set[str] = set()

    for _gkey, txns in grouped.items():
        txns_sorted = sorted(txns, key=lambda x: x["date"])
        merchant = txns_sorted[0].get("merchant") or "Unknown"
        institution = txns_sorted[0].get("institution") or ""
        source_type = txns_sorted[0].get("source_type") or ""
        source_name = _source_label(institution, source_type)
        all_descs = " ".join(t["description"] for t in txns_sorted)
        early_blob = f"{merchant} {all_descs}".lower()

        # ── Single-occurrence path for explicitly labeled EMI/loan payments ──
        # Bank statement uploads may only cover 1 month, so we can't require a
        # multi-month streak. Instead, if the narration/merchant unambiguously
        # indicates an EMI (e.g. "EMI AUTO DEBIT CAR LOAN"), we accept 1 entry.
        if len(txns_sorted) == 1:
            is_explicit = any(k in early_blob for k in _EXPLICIT_EMI_TRIGGERS)
            tx = txns_sorted[0]
            tx_amount = float(tx["amount"] or 0)
            if is_explicit and tx_amount >= 1000:
                m_blob = merchant.lower()
                if not any(k in m_blob for k in SUBSCRIPTION_SKIP):
                    emi_type = _classify_emi_type(
                        merchant=merchant,
                        category=tx["category"],
                        amount=tx_amount,
                        description_blob=tx["description"],
                    )
                    emi_entries.append(
                        {
                            "merchant": merchant,
                            "amount": round(tx_amount, 2),
                            "payment_date": tx["date"].day,
                            "category": tx["category"],
                            "emi_type": emi_type,
                            "months_detected": 1,
                            "first_detected": tx["date"].isoformat(),
                            "last_detected": tx["date"].isoformat(),
                            "next_due": _next_due_date(tx["date"].day, date.today()).isoformat(),
                            "source_name": source_name,
                            "source_type": source_type,
                        }
                    )
                    seen_merchants.add(merchant)
            continue  # always skip to next merchant after single-entry check

        amounts = [x["amount"] for x in txns_sorted]
        dates = [x["date"] for x in txns_sorted]
        categories = [x["category"] for x in txns_sorted]
        descriptions = [x["description"] for x in txns_sorted]

        med_amount = float(median(amounts))
        med_day = int(round(median([d.day for d in dates])))
        if med_amount <= 0:
            continue

        amount_ok = _amounts_plausible(amounts, med_amount)
        if not amount_ok:
            continue
        date_ok = _dates_plausible(dates, med_day)
        if not date_ok:
            continue
        streak, streak_start, streak_end = _longest_consecutive_month_streak(dates)
        if streak < 2:
            continue

        keyword_blob = f"{merchant} {' '.join(descriptions)}".lower()
        has_keyword = any(
            k in keyword_blob
            for k in ("emi", "loan", "equated", "installment", "mortgage", "housing", "nach", "ecs", "repayment")
        )
        merchant_blob = merchant.lower()
        if any(k in merchant_blob for k in SUBSCRIPTION_SKIP):
            continue
        merchant_finance = any(k in merchant_blob for k in MERCHANT_FINANCE_HINTS)
        finance_category = any("finance" in (c or "").lower() for c in categories) and any(
            k in merchant_blob for k in ("loan", "emi", "capital", "financial", "housing", "bank", "ltd")
        )

        if not (has_keyword or finance_category or (merchant_finance and med_amount >= 1200)):
            continue

        emi_type = _classify_emi_type(
            merchant=merchant,
            category=categories[0] if categories else "",
            amount=med_amount,
            description_blob=" ".join(descriptions),
        )
        emi_entries.append(
            {
                "merchant": merchant,
                "amount": round(med_amount, 2),
                "payment_date": med_day,
                "category": categories[0] if categories else "",
                "emi_type": emi_type,
                "months_detected": streak,
                "first_detected": streak_start.isoformat(),
                "last_detected": streak_end.isoformat(),
                "next_due": _next_due_date(med_day, date.today()).isoformat(),
                "source_name": source_name,
                "source_type": source_type,
            }
        )

    cur_burden = conn.cursor()
    try:
        _append_card_statement_burden(cur_burden, user_id, mode, emi_entries)
    finally:
        cur_burden.close()

    emi_entries.sort(key=lambda x: x["amount"], reverse=True)
    total_burden = round(sum(x["amount"] for x in emi_entries), 2)
    ratio = round((total_burden / monthly_income * 100), 1) if monthly_income > 0 else 0.0
    danger = _danger_from_ratio(ratio)
    over_limit = round(max(0.0, ratio - 30.0), 1)
    max_new_emi = round(monthly_income * 0.30 - total_burden, 2)

    verdict: str
    if not emi_entries:
        verdict = "No fixed EMI pattern detected in the last 6 months."
    elif max_new_emi < 0:
        verdict = (
            f"You are Rs.{abs(int(round(max_new_emi))):,} over the safe EMI limit. "
            "Do NOT take any new loans."
        )
    else:
        verdict = (
            f"You can safely take up to Rs.{int(round(max_new_emi)):,} additional EMI "
            "while staying under RBI's 30% guideline."
        )

    advice_prompt = f"""
User: {user_name}
Monthly income: Rs.{monthly_income:,.0f}
Detected EMIs: {emi_entries}
Total EMI burden: Rs.{total_burden:,.0f}
Debt-to-income ratio: {ratio}%
Danger level: {danger}
RBI safe limit: 30%
Give concise practical Indian personal-finance advice in 2-3 sentences.
"""
    advice = call_gpt(
        system_prompt=(
            "You are SmartSpend EMI advisor. Analyze EMI burden and give clear advice in professional English. "
            "Reference specific rupee amounts. Plain text only, max 4 sentences."
        ),
        user_prompt=advice_prompt.strip(),
        max_tokens=220,
        json_mode=False,
    )
    raw = str(advice).strip() if isinstance(advice, str) else ""
    if raw.startswith("AI insights unavailable"):
        raw = ""
    ai_advice = raw or (
        f"Your debt-to-income ratio is {ratio:.1f}%. Keep total EMI commitments under 30% of monthly income "
        f"for stability. With Rs.{total_burden:,.0f} in EMIs on Rs.{monthly_income:,.0f} income, "
        "avoid new loans until the ratio improves."
    )

    return {
        "user_name": user_name,
        "monthly_income": round(monthly_income, 2),
        "emis_detected": emi_entries,
        "total_emi_burden": total_burden,
        "debt_to_income_ratio": ratio,
        "danger_level": danger,
        "rbi_safe_limit": 30,
        "over_limit_by": over_limit,
        "max_new_emi_allowed": max_new_emi,
        "verdict": verdict,
        "ai_advice": ai_advice,
    }


@router.get("/{user_id}")
def get_emi_report(user_id: int, conn=Depends(get_db)):
    try:
        return _build_emi_detection(conn, user_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"EMI detector error: {exc}") from exc


class CalculateImpactBody(BaseModel):
    new_emi_monthly: float = Field(default=0, ge=0, le=5_000_000)


@router.post("/{user_id}/calculate-impact")
def post_calculate_emi_impact(user_id: int, body: CalculateImpactBody, conn=Depends(get_db)):
    """Return DTI before/after adding a hypothetical monthly EMI."""
    try:
        report = _build_emi_detection(conn, user_id)
        inc = float(report.get("monthly_income") or 0)
        if inc <= 0:
            inc = 1.0
        cur_total = float(report.get("total_emi_burden") or 0)
        add = float(body.new_emi_monthly or 0)
        new_total = cur_total + add
        cur_ratio = float(report.get("debt_to_income_ratio") or 0)
        new_ratio = round((new_total / inc) * 100, 1)

        if new_ratio < 25:
            verdict = "SAFE"
            advice = (
                "This EMI keeps your debt load in a comfortable band. Maintain an emergency fund "
                "before adding more obligations."
            )
        elif new_ratio < 30:
            verdict = "CAUTION"
            advice = (
                "You are approaching the RBI-style 30% EMI-to-income guideline. "
                "Avoid further loans until income grows or existing EMIs shrink."
            )
        elif new_ratio < 40:
            verdict = "RISKY"
            advice = (
                "This pushes you above the 30% safe line. Only proceed if the loan is essential "
                "and you have surplus savings."
            )
        else:
            verdict = "DANGER"
            advice = (
                "Debt servicing would consume a dangerous share of income. "
                "Do not take this EMI unless you restructure existing debt first."
            )

        return {
            "new_emi_monthly": round(add, 2),
            "current_ratio": cur_ratio,
            "new_ratio": new_ratio,
            "current_total_burden": round(cur_total, 2),
            "new_total_burden": round(new_total, 2),
            "monthly_income": round(inc, 2),
            "verdict": verdict,
            "advice": advice,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"calculate-impact error: {exc}") from exc


def _add_months_clamped(d: date, months: int) -> date:
    m0 = d.month - 1 + months
    y = d.year + m0 // 12
    mo = m0 % 12 + 1
    last = calendar.monthrange(y, mo)[1]
    return date(y, mo, min(d.day, last))


def _load_active_purchase_goals(cur, user_id: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, item_name, COALESCE(monthly_target, 0)::float, target_date, COALESCE(priority, 'MEDIUM'), status
        FROM purchase_goals
        WHERE user_id = %s
          AND UPPER(COALESCE(status, '')) NOT IN ('CANCELLED', 'COMPLETED');
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for gid, name, monthly, td, priority, status in rows:
        if isinstance(td, date):
            td_d = td
        else:
            td_d = datetime.strptime(str(td)[:10], "%Y-%m-%d").date()
        pr = str(priority or "MEDIUM").upper()
        out.append(
            {
                "goal_id": int(gid),
                "goal_name": str(name),
                "monthly_target": float(monthly or 0),
                "target_date": td_d.isoformat(),
                "priority": pr,
                "status": str(status or ""),
            }
        )
    return out


def _user_fixed_expenses(conn, user_id: int) -> float:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COALESCE(monthly_fixed_expenses, 0)::float
            FROM users WHERE id = %s;
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return 2000.0
        v = float(row[0] or 0)
        return v if v > 0 else 2000.0
    except Exception:
        conn.rollback()
        return 2000.0
    finally:
        cur.close()


def _build_affordability(conn, user_id: int, new_emi_monthly: float) -> dict[str, Any]:
    report = _build_emi_detection(conn, user_id)
    income = float(report.get("monthly_income") or 0)
    if income <= 0:
        income = 1.0
    user_name = str(report.get("user_name") or "You").strip()
    total_emi = float(report.get("total_emi_burden") or 0)
    emi_ratio = float(report.get("debt_to_income_ratio") or 0)

    fixed = _user_fixed_expenses(conn, user_id)
    cur = conn.cursor()
    try:
        goals = _load_active_purchase_goals(cur, user_id)
    finally:
        cur.close()

    goals_monthly = sum(g["monthly_target"] for g in goals)
    current_commit = total_emi + goals_monthly + fixed
    new_commit = current_commit + float(new_emi_monthly or 0)

    oblig_ratio_cur = round((current_commit / income) * 100, 1)
    oblig_ratio_new = round((new_commit / income) * 100, 1)
    new_emi_only_ratio = round(((total_emi + float(new_emi_monthly or 0)) / income) * 100, 1)

    if oblig_ratio_new > 50:
        risk = "critical"
        can_afford = False
    elif oblig_ratio_new > 40:
        risk = "high"
        can_afford = False
    elif oblig_ratio_new > 35:
        risk = "medium"
        can_afford = True
    else:
        risk = "low"
        can_afford = True

    headroom = round(income - new_commit, 2)

    suggestions: list[dict[str, str]] = []
    if oblig_ratio_new > 50:
        suggestions.append(
            {
                "type": "reject_or_restructure",
                "message": (
                    "Taking this EMI pushes total monthly commitments above 50% of income — "
                    "very little room for emergencies or income shocks."
                ),
            }
        )
    elif oblig_ratio_new > 40:
        suggestions.append(
            {
                "type": "warning",
                "message": (
                    "This EMI stretches your plan: EMIs + savings goals + essentials use a large share of income. "
                    "Consider trimming non-urgent goals or waiting."
                ),
            }
        )

    postpone_options: list[dict[str, Any]] = []
    if not can_afford and goals:
        today = date.today()
        for g in goals:
            if g["priority"] == "HIGH":
                continue
            freed = float(g["monthly_target"] or 0)
            if freed <= 0:
                continue
            alt_commit = new_commit - freed
            alt_ratio = round((alt_commit / income) * 100, 1)
            if alt_ratio >= oblig_ratio_new:
                continue
            gap = max(0.0, new_commit - 0.45 * income)
            months_post = max(3, min(18, int(math.ceil(gap / max(freed, 1))) if gap > 0 else 3))
            try:
                old_td = datetime.strptime(g["target_date"][:10], "%Y-%m-%d").date()
            except ValueError:
                old_td = today
            new_td = _add_months_clamped(old_td, months_post)
            postpone_options.append(
                {
                    "goal_id": g["goal_id"],
                    "goal_name": g["goal_name"],
                    "current_monthly_saving": round(freed, 2),
                    "current_target_date": g["target_date"],
                    "suggested_new_date": new_td.isoformat(),
                    "months_postponed": months_post,
                    "reasoning": (
                        f"Pausing monthly savings toward “{g['goal_name']}” (₹{freed:,.0f}/mo) "
                        f"reduces planned commitments so a new EMI is less risky."
                    ),
                    "obligation_ratio_if_postponed": alt_ratio,
                }
            )

    if oblig_ratio_new > 50:
        title = f"{user_name}, this EMI is financially risky"
        summary = (
            f"With this ₹{new_emi_monthly:,.0f}/mo EMI, total planned outflows reach about "
            f"₹{new_commit:,.0f}/mo (~{oblig_ratio_new:.0f}% of take-home). That leaves little buffer for emergencies."
        )
        recommendation = "POSTPONE_OR_REJECT"
        reasoning = [
            "Combined EMIs, goals, and fixed costs would consume a large share of income.",
            "Medical or family surprises become harder to absorb without new debt.",
            "If income dips, servicing existing loans gets stressful.",
        ]
    elif oblig_ratio_new > 40:
        title = f"{user_name}, this EMI is tight but may be workable"
        summary = (
            f"You would still have about ₹{max(0, income - new_commit):,.0f}/mo after all planned commitments — "
            "thin cushion for savings spikes or emergencies."
        )
        recommendation = "PROCEED_WITH_CAUTION"
        reasoning = [
            "Above the ~40% “all-in commitment” comfort band for many households.",
            "Build or keep a 3–6 month emergency fund before signing.",
            "Consider postponing a non-urgent purchase goal to widen the buffer.",
        ]
    else:
        title = f"{user_name}, this EMI looks manageable on paper"
        summary = (
            f"After EMIs, goals, and essentials, roughly ₹{max(0, income - new_commit):,.0f}/mo would remain — "
            "ensure that matches your real lifestyle (rent, insurance, irregular bills)."
        )
        recommendation = "PROCEED"
        reasoning = [
            "All-in commitments stay in a healthier band relative to income.",
            "Still review tenure, rate, and prepayment options before committing.",
        ]

    alternative = None
    if postpone_options:
        top = postpone_options[0]
        alternative = (
            f"If you push “{top['goal_name']}” out by about {top['months_postponed']} months "
            f"(new target ~{top['suggested_new_date']}), your stress ratio improves toward ~{top['obligation_ratio_if_postponed']:.0f}%."
        )

    advice_obj: dict[str, Any] = {
        "title": title,
        "summary": summary,
        "recommendation": recommendation,
        "reasoning": reasoning,
    }
    if alternative:
        advice_obj["alternative"] = alternative

    return {
        "user_name": user_name,
        "monthly_income": round(income, 2),
        "monthly_fixed_expenses": round(fixed, 2),
        "total_emi_burden": round(total_emi, 2),
        "total_goal_commitments": round(goals_monthly, 2),
        "current_monthly_commitment": round(current_commit, 2),
        "new_emi_monthly": round(float(new_emi_monthly or 0), 2),
        "new_monthly_commitment": round(new_commit, 2),
        "obligation_ratio_current": oblig_ratio_cur,
        "obligation_ratio_new": oblig_ratio_new,
        "emi_to_income_current": emi_ratio,
        "emi_to_income_new": new_emi_only_ratio,
        "risk_level": risk,
        "can_afford": can_afford,
        "headroom_after_new_emi": headroom,
        "suggestions": suggestions,
        "postpone_options": postpone_options,
        "advice": advice_obj,
        "goals_snapshot": goals,
    }


class AffordabilityBody(BaseModel):
    new_emi_monthly: float = Field(default=0, ge=0, le=5_000_000)


@router.post("/{user_id}/affordability")
def post_emi_affordability(user_id: int, body: AffordabilityBody, conn=Depends(get_db)):
    """
    Full monthly picture: EMIs + purchase-goal savings pace + fixed costs vs income.
    Returns postpone suggestions for Purchase Planner one-click sync.
    """
    try:
        return _build_affordability(conn, user_id, body.new_emi_monthly)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"affordability error: {exc}") from exc


@router.post("/{user_id}/scan")
def scan_and_store_emi(user_id: int, conn=Depends(get_db)):
    try:
        report = _build_emi_detection(conn, user_id)
        entries = report["emis_detected"]
        cur = conn.cursor()
        try:
            cur.execute("UPDATE emi_records SET is_active = FALSE WHERE user_id = %s;", (user_id,))
            for item in entries:
                cur.execute(
                    """
                    INSERT INTO emi_records (
                        user_id, merchant, detected_amount, payment_date, category, emi_type,
                        months_detected, is_active, first_detected, last_detected
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s)
                    ON CONFLICT (user_id, merchant) DO UPDATE SET
                        detected_amount = EXCLUDED.detected_amount,
                        payment_date = EXCLUDED.payment_date,
                        category = EXCLUDED.category,
                        emi_type = EXCLUDED.emi_type,
                        months_detected = EXCLUDED.months_detected,
                        is_active = TRUE,
                        first_detected = EXCLUDED.first_detected,
                        last_detected = EXCLUDED.last_detected;
                    """,
                    (
                        user_id,
                        item["merchant"],
                        item["amount"],
                        item["payment_date"],
                        item["category"],
                        item["emi_type"],
                        item["months_detected"],
                        item["first_detected"],
                        item["last_detected"],
                    ),
                )
        finally:
            cur.close()
        return {
            "user_id": user_id,
            "emi_detected_count": len(entries),
            "total_emi_burden": report["total_emi_burden"],
            "debt_to_income_ratio": report["debt_to_income_ratio"],
            "danger_level": report["danger_level"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"EMI scan error: {exc}") from exc


# ── Affordability Check (inline so this working router always has it) ─────────

class _AffordBody(BaseModel):
    proposed_new_emi: float = Field(..., ge=0, le=5_000_000)


@router.post("/{user_id}/affordability-check")
def post_affordability_check_inline(user_id: int, body: _AffordBody, conn=Depends(get_db)):
    """
    Deterministic EMI affordability: RBI headroom + liquidity vs goals + buffer.
    Inline in emi_detector so the route is guaranteed to be registered.
    """
    try:
        from routes.emi_affordability_check import _build_affordability_check_payload
        return _build_affordability_check_payload(conn, user_id, float(body.proposed_new_emi))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"affordability-check error: {exc}") from exc


# ── Purchase-goal postpone (inline so this working router always has it) ──────

class _PostponeByMonthsBody(BaseModel):
    postpone_months: int = Field(..., ge=1, le=60)


class _PostponeToDateBody(BaseModel):
    new_target_date: str = Field(..., min_length=8, max_length=12)
    reason: str = Field(default="", max_length=500)
    festival_key: str = Field(default="", max_length=50)
    display_timeline_label: str = Field(default="", max_length=80)


@router.post("/{user_id}/purchase/{goal_id}/postpone-months")
def postpone_goal_months_inline(user_id: int, goal_id: int, body: _PostponeByMonthsBody, conn=Depends(get_db)):
    """Shift purchase goal target_date by N months. Inline route always present."""
    try:
        from routes.purchase_planner import postpone_goal_by_months, PostponeMonthsBody
        return postpone_goal_by_months(user_id, goal_id, PostponeMonthsBody(postpone_months=body.postpone_months), conn)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"postpone error: {exc}") from exc


@router.post("/{user_id}/purchase/{goal_id}/postpone-date")
def postpone_goal_date_inline(user_id: int, goal_id: int, body: _PostponeToDateBody, conn=Depends(get_db)):
    """Move purchase goal to a specific date. Inline route always present."""
    try:
        from routes.purchase_planner import postpone_purchase_goal, PostponeGoalBody
        b = PostponeGoalBody(
            new_target_date=body.new_target_date,
            reason=body.reason or "Postponed from EMI Tracker.",
            festival_key=body.festival_key or None,
            display_timeline_label=body.display_timeline_label or None,
        )
        return postpone_purchase_goal(user_id, goal_id, b, conn)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"postpone-date error: {exc}") from exc
