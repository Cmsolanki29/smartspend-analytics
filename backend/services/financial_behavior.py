"""Planning + EMI snapshot for health score and AI insights (all users)."""

from __future__ import annotations

from datetime import date
from typing import Any


def _months_until(from_d: date, to_d: date) -> int:
    if to_d <= from_d:
        return 1
    m = (to_d.year - from_d.year) * 12 + to_d.month - from_d.month
    if to_d.day < from_d.day:
        m -= 1
    return max(1, m)


def _table_exists(cur, table: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        LIMIT 1;
        """,
        (table,),
    )
    return cur.fetchone() is not None


def _norm_merchant(s: str) -> str:
    return " ".join((s or "").lower().split())


def _merchant_dismissed(label: str, dismissed_labels: set[str]) -> bool:
    """True if this EMI label was dismissed by the user (tracker remove)."""
    lab = _norm_merchant(label)
    if not lab:
        return False
    for d in dismissed_labels:
        dn = _norm_merchant(d)
        if not dn:
            continue
        if lab == dn or dn in lab or lab in dn:
            return True
    return False


def _load_dismissed_festival_keys(cur, user_id: int) -> set[tuple[str, str]]:
    """(normalized_name, iso_date) removed from festival planner."""
    keys: set[tuple[str, str]] = set()
    if not _table_exists(cur, "festival_dismissals"):
        return keys
    try:
        cur.execute(
            """
            SELECT festival_name, festival_date::date
            FROM festival_dismissals WHERE user_id = %s;
            """,
            (user_id,),
        )
        for name, fd in cur.fetchall():
            if name and fd:
                d = fd if isinstance(fd, date) else date.fromisoformat(str(fd)[:10])
                keys.add((_norm_merchant(str(name)), d.isoformat()))
    except Exception:
        pass
    return keys


def _load_dismissed_merchants(cur, user_id: int) -> set[str]:
    labels: set[str] = set()
    if not _table_exists(cur, "emi_dismissals"):
        return labels
    try:
        cur.execute(
            """
            SELECT merchant_label FROM emi_dismissals WHERE user_id = %s;
            """,
            (user_id,),
        )
        for (lbl,) in cur.fetchall():
            if lbl:
                labels.add(str(lbl))
    except Exception:
        pass
    return labels


def fetch_planning_snapshot(
    cur,
    user_id: int,
    *,
    income_basis: float = 0.0,
) -> dict[str, Any]:
    """
    EMI burden, purchase goals, festival budgets, upcoming important days.
    Respects emi_dismissals so removing an EMI improves health score.
    """
    today = date.today()
    dismissed = _load_dismissed_merchants(cur, user_id)
    dismissed_festivals = _load_dismissed_festival_keys(cur, user_id)

    snap: dict[str, Any] = {
        "emi_monthly_total": 0.0,
        "emi_count": 0,
        "emi_burden_pct": None,
        "purchase_monthly_reserve": 0.0,
        "festival_monthly_reserve": 0.0,
        "events_monthly_reserve": 0.0,
        "planning_burden_pct": None,
        "active_purchase_goals": 0,
        "purchase_goals_on_track": 0,
        "purchase_goal_progress_pct": None,
        "active_festivals": 0,
        "festival_progress_pct": None,
        "upcoming_important_days": 0,
        "has_planning_data": False,
    }

    emi_total = 0.0
    emi_count = 0
    seen_emi_merchants: set[str] = set()

    def _add_emi(name: str, amt: float) -> None:
        nonlocal emi_total, emi_count
        norm = _norm_merchant(name)
        if not norm or _merchant_dismissed(name, dismissed):
            return
        if norm in seen_emi_merchants:
            return
        seen_emi_merchants.add(norm)
        emi_total += float(amt or 0)
        emi_count += 1

    if _table_exists(cur, "emis"):
        cur.execute(
            """
            SELECT COALESCE(loan_name, ''), COALESCE(emi_amount, 0)::float
            FROM emis
            WHERE user_id = %s AND LOWER(COALESCE(status, 'active')) = 'active';
            """,
            (user_id,),
        )
        for loan_name, amt in cur.fetchall():
            _add_emi(str(loan_name or ""), float(amt or 0))

    if _table_exists(cur, "emi_records"):
        cur.execute(
            """
            SELECT COALESCE(merchant, ''), COALESCE(detected_amount, 0)::float
            FROM emi_records
            WHERE user_id = %s AND COALESCE(is_active, TRUE) = TRUE;
            """,
            (user_id,),
        )
        for merchant, amt in cur.fetchall():
            _add_emi(str(merchant or ""), float(amt or 0))

    snap["emi_monthly_total"] = round(emi_total, 2)
    snap["emi_count"] = emi_count

    purchase_reserve = 0.0
    purchase_progress: list[float] = []
    if _table_exists(cur, "purchase_goals"):
        cur.execute(
            """
            SELECT COALESCE(monthly_target, 0)::float,
                   COALESCE(target_amount, 0)::float,
                   COALESCE(saved_amount, 0)::float,
                   target_date
            FROM purchase_goals
            WHERE user_id = %s
              AND UPPER(COALESCE(status, '')) NOT IN ('COMPLETED', 'CANCELLED', 'PAUSED');
            """,
            (user_id,),
        )
        for mt, target_amt, saved_amt, target_date in cur.fetchall():
            target_f = float(target_amt or 0)
            saved_f = float(saved_amt or 0)
            td = (
                target_date
                if isinstance(target_date, date)
                else date.fromisoformat(str(target_date)[:10])
            )
            months_rem = _months_until(today, td)
            remaining = max(0.0, target_f - saved_f)
            computed_mt = remaining / months_rem if months_rem else remaining
            monthly = float(mt or 0)
            if monthly <= 0 and computed_mt > 0:
                monthly = computed_mt
            purchase_reserve += monthly
            snap["active_purchase_goals"] += 1
            if target_f > 0:
                purchase_progress.append(min(1.0, saved_f / target_f))
            if monthly > 0 and remaining > 0:
                pace = saved_f / max(target_f, 1.0)
                expected = 1.0 - (remaining / target_f)
                if pace >= max(0.0, expected - 0.12):
                    snap["purchase_goals_on_track"] += 1

    snap["purchase_monthly_reserve"] = round(purchase_reserve, 2)
    if purchase_progress:
        snap["purchase_goal_progress_pct"] = round(
            sum(purchase_progress) / len(purchase_progress) * 100, 1
        )

    festival_reserve = 0.0
    fest_progress: list[float] = []
    if _table_exists(cur, "festival_budgets"):
        cur.execute(
            """
            SELECT festival_name, festival_date,
                   COALESCE(monthly_target, 0)::float,
                   COALESCE(planned_budget, 0)::float,
                   COALESCE(saved_so_far, 0)::float
            FROM festival_budgets
            WHERE user_id = %s
              AND festival_date >= CURRENT_DATE
              AND UPPER(COALESCE(status, 'UPCOMING')) <> 'COMPLETED';
            """,
            (user_id,),
        )
        for fname, fdate, monthly_tgt, planned, saved in cur.fetchall():
            d = fdate if isinstance(fdate, date) else date.fromisoformat(str(fdate)[:10])
            fkey = (_norm_merchant(str(fname or "")), d.isoformat())
            if fkey in dismissed_festivals:
                continue
            snap["active_festivals"] += 1
            planned_f = float(planned or 0)
            saved_f = float(saved or 0)
            monthly = float(monthly_tgt or 0)
            if monthly <= 0 and planned_f > 0:
                months_rem = _months_until(today, d)
                monthly = max(0.0, planned_f - saved_f) / months_rem
            festival_reserve += monthly
            if planned_f > 0:
                fest_progress.append(min(1.0, saved_f / planned_f))
            elif saved_f > 0:
                fest_progress.append(1.0)

    snap["festival_monthly_reserve"] = round(festival_reserve, 2)
    if fest_progress:
        snap["festival_progress_pct"] = round(sum(fest_progress) / len(fest_progress) * 100, 1)

    events_reserve = 0.0
    upcoming = 0
    if _table_exists(cur, "user_important_days"):
        try:
            cur.execute(
                """
                SELECT COALESCE(estimated_budget, 0)::float, event_date
                FROM user_important_days
                WHERE user_id = %s
                  AND event_date >= CURRENT_DATE
                  AND event_date <= CURRENT_DATE + INTERVAL '90 days';
                """,
                (user_id,),
            )
            day_rows = cur.fetchall()
        except Exception:
            cur.execute(
                """
                SELECT 0::float, event_date
                FROM user_important_days
                WHERE user_id = %s
                  AND event_date >= CURRENT_DATE
                  AND event_date <= CURRENT_DATE + INTERVAL '90 days';
                """,
                (user_id,),
            )
            day_rows = cur.fetchall()
        for budget, ev_date in day_rows:
            upcoming += 1
            ev = ev_date if isinstance(ev_date, date) else today
            months = _months_until(today, ev)
            b = float(budget or 0)
            if b > 0:
                events_reserve += b / months
            elif income_basis > 0:
                events_reserve += income_basis * 0.02
            else:
                events_reserve += 1500.0

    snap["events_monthly_reserve"] = round(events_reserve, 2)
    snap["upcoming_important_days"] = upcoming

    if income_basis > 0:
        burden = emi_total + purchase_reserve + festival_reserve + events_reserve
        snap["planning_burden_pct"] = round(burden / income_basis * 100, 1)
        if emi_total > 0:
            snap["emi_burden_pct"] = round(emi_total / income_basis * 100, 1)

    snap["has_planning_data"] = (
        emi_count > 0
        or snap["active_purchase_goals"] > 0
        or snap["active_festivals"] > 0
        or snap["upcoming_important_days"] > 0
    )
    return snap


def score_emi_points(emi_burden_pct: float | None) -> int:
    """No EMI load (None or 0%) is best — removing EMIs should not lower this bucket."""
    if emi_burden_pct is None or float(emi_burden_pct) <= 0:
        return 17
    if emi_burden_pct <= 15:
        return 17
    if emi_burden_pct <= 25:
        return 13
    if emi_burden_pct <= 35:
        return 8
    if emi_burden_pct <= 50:
        return 4
    return 0


def _planning_burden_points(burden_pct: float) -> int:
    """How heavy EMIs + purchase + festival monthly targets are vs income (max 9)."""
    if burden_pct <= 12:
        return 9
    if burden_pct <= 22:
        return 7
    if burden_pct <= 32:
        return 5
    if burden_pct <= 45:
        return 3
    if burden_pct <= 60:
        return 1
    return 0


def _planning_progress_points(snap: dict[str, Any]) -> int:
    """Reward saving progress in Purchase + Festival planners (max 6)."""
    if not snap.get("has_planning_data"):
        return 0
    parts: list[float] = []
    fp = snap.get("festival_progress_pct")
    pp = snap.get("purchase_goal_progress_pct")
    if fp is not None:
        parts.append(float(fp))
    if pp is not None:
        parts.append(float(pp))
    if not parts:
        n = int(snap.get("active_purchase_goals") or 0) + int(snap.get("active_festivals") or 0)
        return 2 if n > 0 else 0
    avg = sum(parts) / len(parts)
    on_track = int(snap.get("purchase_goals_on_track") or 0)
    goals_n = int(snap.get("active_purchase_goals") or 0)
    if avg >= 75:
        base = 6
    elif avg >= 50:
        base = 4
    elif avg >= 25:
        base = 2
    else:
        base = 1
    if goals_n > 0 and on_track >= max(1, goals_n // 2):
        base = min(6, base + 1)
    return base


def score_planning_points(snap: dict[str, Any], income_basis: float = 0.0) -> int:
    """
    Goals & events = burden vs income (9 pts) + planner progress (6 pts).
    Updating savings / lowering targets should move this bucket within ~1–2 pts.
    """
    if income_basis <= 0:
        return 10 if snap.get("has_planning_data") else 8

    burden_pct = snap.get("planning_burden_pct")
    if burden_pct is None:
        emi = float(snap.get("emi_monthly_total") or 0)
        purchase = float(snap.get("purchase_monthly_reserve") or 0)
        fest = float(snap.get("festival_monthly_reserve") or 0)
        events = float(snap.get("events_monthly_reserve") or 0)
        burden_pct = (emi + purchase + fest + events) / income_basis * 100

    burden_pct = float(burden_pct or 0)
    return min(15, _planning_burden_points(burden_pct) + _planning_progress_points(snap))
