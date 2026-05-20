#!/usr/bin/env python3
"""
Generate onboarding upload CSVs for team demo signups (Chirag, Amruta, Sumit, Ganesh).

Does NOT touch vikram@smartspend.in / priya@ / rahul@ / ananya@ / karan@ DB seed data.
Output: test samples/onboarding/*.csv

Run from repo root:
  python backend/scripts/generate_team_onboarding_statements.py
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "test samples" / "onboarding"

BankFmt = Literal["hdfc", "icici", "axis", "sbi"]


@dataclass
class Persona:
    key: str
    full_name: str
    salary: float
    rent: float
    city: str
    employer: str
    bank_fmt: BankFmt
    bank_label: str
    account_suffix: str
    # recurring debits (day_of_month, amount, narration_key)
    emis: list[tuple[int, float, str]] = field(default_factory=list)
    subs: list[tuple[int, float, str]] = field(default_factory=list)
    utilities: list[tuple[int, float, str]] = field(default_factory=list)
    rng_seed: int = 0


PERSONAS: tuple[Persona, ...] = (
    Persona(
        key="chirag",
        full_name="Chirag Solanki",
        salary=92_000,
        rent=22_000,
        city="Pune",
        employer="EXIQO TECHNOLOGIES PVT LTD",
        bank_fmt="hdfc",
        bank_label="HDFC Bank",
        account_suffix="4821",
        emis=[(5, 7_083, "EMI iPhone 15 Pro Max"), (5, 8_916, "EMI MacBook Air M2")],
        subs=[
            (8, 999, "LinkedIn Premium"),
            (11, 499, "Canva Pro"),
            (14, 119, "Spotify Premium"),
            (18, 129, "YouTube Premium"),
            (20, 125, "Amazon Prime"),
            (22, 1_999, "ChatGPT Plus"),
        ],
        utilities=[(3, 1_850, "MSEDCL Electricity Pune"), (4, 999, "JioFiber 300Mbps")],
        rng_seed=92001,
    ),
    Persona(
        key="amruta",
        full_name="Amruta Abhangrao",
        salary=75_000,
        rent=28_000,
        city="Mumbai",
        employer="INFOSYS LTD",
        bank_fmt="icici",
        bank_label="ICICI Bank",
        account_suffix="7733",
        emis=[
            (5, 15_000, "EMI Home Renovation Loan"),
            (5, 4_200, "EMI Honda Activa 6G"),
            (6, 6_800, "EMI Personal Loan Medical"),
        ],
        subs=[
            (7, 649, "Netflix Standard"),
            (12, 49, "Zepto Pass"),
            (15, 179, "Spotify Family"),
            (25, 125, "Amazon Prime"),
        ],
        utilities=[(3, 1_600, "MSEDCL Mumbai"), (4, 799, "Airtel Broadband")],
        rng_seed=75002,
    ),
    Persona(
        key="sumit",
        full_name="Sumit Dabas",
        salary=45_000,
        rent=15_000,
        city="Bengaluru",
        employer="WIPRO LTD",
        bank_fmt="axis",
        bank_label="Axis Bank",
        account_suffix="3390",
        emis=[(5, 3_200, "EMI Dell XPS Laptop")],
        subs=[(10, 199, "Netflix Mobile"), (20, 99, "JioSaavn Pro")],
        utilities=[(3, 850, "BESCOM Electricity"), (4, 799, "Airtel Broadband"), (6, 239, "Jio Mobile Recharge")],
        rng_seed=45003,
    ),
    Persona(
        key="ganesh",
        full_name="Ganesh Patil",
        salary=140_000,
        rent=25_000,
        city="Chennai",
        employer="TCS LTD",
        bank_fmt="sbi",
        bank_label="State Bank of India",
        account_suffix="9102",
        emis=[(5, 22_000, "EMI Hyundai Creta SX")],
        subs=[
            (5, 649, "Netflix 4K"),
            (12, 119, "Spotify Premium"),
            (4, 49, "Zepto Pass"),
            (18, 1_675, "Adobe Creative Cloud"),
            (25, 125, "Amazon Prime"),
        ],
        utilities=[(3, 2_400, "TNEB Electricity Chennai"), (4, 999, "JioFiber 500Mbps")],
        rng_seed=140004,
    ),
)


@dataclass
class Txn:
    d: date
    kind: Literal["credit", "debit"]
    amount: float
    desc: str


def _months() -> list[date]:
    """Feb–May 2026 (May partial through 14th)."""
    out: list[date] = []
    for y, m in ((2026, 2), (2026, 3), (2026, 4), (2026, 5)):
        last = 14 if (y, m) == (2026, 5) else 28
        out.append(date(y, m, 1))
    return out


def _month_label(d: date) -> str:
    return d.strftime("%b").upper()[:3] + d.strftime("%y")


def build_persona_txns(p: Persona) -> list[Txn]:
    rng = random.Random(p.rng_seed)
    txns: list[Txn] = []

    food_pool = [
        ("Swiggy", 280, 560),
        ("Zomato", 320, 520),
    ]
    transport_pool = [
        ("Uber", 120, 340),
        ("Ola Cabs", 110, 310),
        ("Rapido", 45, 120),
    ]
    if p.city == "Mumbai":
        transport_pool += [("Mumbai Local", 180, 180), ("Auto Rickshaw", 65, 110)]
    elif p.city == "Bengaluru":
        transport_pool += [("Namma Metro", 65, 65), ("Rapido", 55, 95)]
    elif p.city == "Chennai":
        transport_pool += [("Chennai Metro", 55, 80)]

    grocery_pool = [
        ("BigBasket", 1200, 2200),
        ("DMart", 1100, 2100),
        ("Zepto", 900, 1600),
    ]
    shop_pool = [
        ("Amazon", 800, 3500),
        ("Flipkart", 700, 2800),
        ("Myntra", 900, 3200),
    ]

    for month_start in _months():
        ml = _month_label(month_start)
        y, m = month_start.year, month_start.month
        last_day = 14 if (y, m) == (2026, 5) else 28

        txns.append(
            Txn(
                date(y, m, 1),
                "credit",
                p.salary,
                f"Salary Credit - {p.full_name} - {ml}",
            )
        )
        txns.append(
            Txn(
                date(y, m, 2),
                "debit",
                p.rent,
                f"Monthly Rent {p.city} - {ml}",
            )
        )

        for day, amt, label in p.utilities:
            if day <= last_day:
                txns.append(Txn(date(y, m, day), "debit", amt, label))

        for day, amt, label in p.emis:
            if day <= last_day:
                txns.append(
                    Txn(
                        date(y, m, day),
                        "debit",
                        amt,
                        f"{label} - {p.bank_label} AutoDebit",
                    )
                )

        for day, amt, label in p.subs:
            if day <= last_day:
                txns.append(Txn(date(y, m, day), "debit", amt, label))

        # Daily-ish spends
        spend_days = [d for d in range(3, last_day + 1) if d % 2 == 1 or d % 5 == 0]
        for day in spend_days:
            merch, lo, hi = rng.choice(food_pool)
            txns.append(
                Txn(
                    date(y, m, day),
                    "debit",
                    float(rng.randint(lo, hi)),
                    f"UPI {merch} Food Order {p.city}",
                )
            )
            if day % 4 == 1:
                merch, lo, hi = rng.choice(transport_pool)
                txns.append(
                    Txn(
                        date(y, m, day),
                        "debit",
                        float(rng.randint(lo, hi)),
                        f"UPI {merch} {p.city}",
                    )
                )
            if day % 6 == 2:
                merch, lo, hi = rng.choice(grocery_pool)
                txns.append(
                    Txn(
                        date(y, m, day),
                        "debit",
                        float(rng.randint(lo, hi)),
                        f"UPI {merch} Grocery",
                    )
                )
            if day % 7 == 3:
                merch, lo, hi = rng.choice(shop_pool)
                txns.append(
                    Txn(
                        date(y, m, day),
                        "debit",
                        float(rng.randint(lo, hi)),
                        f"UPI {merch} Shopping",
                    )
                )

        # Entertainment / medical sprinkling
        if last_day >= 9:
            txns.append(Txn(date(y, m, 9), "debit", float(rng.randint(400, 900)), f"PVR Cinemas {p.city}"))
        if last_day >= 16:
            txns.append(Txn(date(y, m, 16), "debit", float(rng.randint(350, 750)), f"BookMyShow {p.city}"))
        if last_day >= 12:
            txns.append(
                Txn(
                    date(y, m, 12),
                    "debit",
                    float(rng.randint(450, 1200)),
                    f"Apollo Pharmacy {p.city}",
                )
            )

    # One mild fraud-flag row for Chirag demo (FraudShield)
    if p.key == "chirag":
        txns.append(
            Txn(
                date(2026, 4, 12),
                "debit",
                48_500.0,
                "UPI CRYPTOX EXCHANGE DUBAI cryptox@ybl YESBANK",
            )
        )

    txns.sort(key=lambda t: (t.d, 0 if t.kind == "credit" else 1))
    return txns


# --- HDFC writer ---
def write_hdfc(path: Path, p: Persona, txns: list[Txn]) -> None:
    bal = 85_000.0
    refn = int(f"9{p.rng_seed}"[:9])
    rows: list[list[str]] = []
    for t in txns:
        ref = f"N{refn}"
        refn += 1
        vd = t.d.strftime("%d/%m/%y")
        if t.kind == "credit":
            nar = f"NEFT-HDFC0001234-{p.employer}-SALARY {_month_label(t.d)}-{ref}"
            if "Salary" in t.desc:
                nar = f"NEFT-HDFC0001234-{p.employer}-SALARY {_month_label(t.d)}-{ref}"
            else:
                nar = t.desc[:120]
            bal += t.amount
            rows.append([vd, nar, ref, vd, "", f"{t.amount:.2f}", f"{bal:.2f}"])
        else:
            if "Rent" in t.desc:
                nar = f"NEFT DR-SBIN0012345-LANDLORD RENT {_month_label(t.d)}-{ref[-9:]}"
            elif "EMI" in t.desc:
                nar = f"ACH DR-{t.desc.upper()}-{ref[-9:]}"
            elif "UPI" in t.desc:
                nar = t.desc.replace(" ", "-")[:100] + f"-{ref[-6:]}"
            else:
                nar = f"UPI-{t.desc[:40]}-pay@ybl-PAYTMBANK-{ref[-6:]}"
            bal -= t.amount
            rows.append([vd, nar, ref, vd, f"{t.amount:.2f}", "", f"{bal:.2f}"])

    _write_csv(
        path,
        ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
        rows,
        header_lines=[
            f"HDFC BANK - Account Statement",
            f"Account Holder : {p.full_name}",
            f"Account No     : XXXX{p.account_suffix}",
            f"Branch         : {p.city}",
            f"Period         : 01/02/2026 to 14/05/2026",
            "",
        ],
    )


def write_icici(path: Path, p: Persona, txns: list[Txn]) -> None:
    bal = 72_000.0
    refn = int(f"7{p.rng_seed}"[:9])
    rows: list[list[str]] = []
    for t in txns:
        ref = str(refn)
        refn += 1
        ds = t.d.strftime("%d-%m-%Y")
        if t.kind == "credit":
            desc = f"NEFT CR {p.employer} SALARY {_month_label(t.d)}"
            bal += t.amount
            rows.append([ds, ds, desc, ref[-10:], "", f"{t.amount:.2f}", f"{bal:.2f}"])
        else:
            if "Rent" in t.desc:
                desc = f"NEFT DR LANDLORD RENT {_month_label(t.d)} N{ref[-9:]}"
            elif "EMI" in t.desc:
                desc = f"ACH DR {t.desc} N{ref[-9:]}"
            else:
                desc = f"UPI/DR/{ref[-12:]}/{t.desc[:40]}/Payment"
            bal -= t.amount
            rows.append([ds, ds, desc, ref[-10:], f"{t.amount:.2f}", "", f"{bal:.2f}"])

    _write_csv(
        path,
        [
            "Transaction Date",
            "Value Date",
            "Description",
            "Cheque Number",
            "Withdrawal Amount (INR)",
            "Deposit Amount (INR)",
            "Available Balance (INR)",
        ],
        rows,
        header_lines=[
            f"ICICI Bank - Statement of Account",
            f"Customer Name: {p.full_name}",
            f"Account Number: XXXX{p.account_suffix}",
            f"City: {p.city}",
            "",
        ],
    )


def write_axis(path: Path, p: Persona, txns: list[Txn]) -> None:
    bal = 38_000.0
    refn = int(f"4{p.rng_seed}"[:9])
    rows: list[list[str]] = []
    for t in txns:
        ref = str(refn)
        refn += 1
        ds = t.d.strftime("%d-%m-%Y")
        if t.kind == "credit":
            part = f"NEFT INWARD-{p.employer}-SALARY {_month_label(t.d)}-N{ref[-6:]}"
            bal += t.amount
            rows.append([ds, part, ref, ds, "", f"{t.amount:.2f}", f"{bal:.2f}"])
        else:
            if "Rent" in t.desc:
                part = f"NEFT OUTWARD-RENT {_month_label(t.d)}-N{ref[-6:]}"
            elif "EMI" in t.desc:
                part = f"ACH DR {t.desc} N{ref[-6:]}"
            else:
                part = f"UPI-{t.desc[:50]}-UPI/{ref[-9:]}/Payment"
            bal -= t.amount
            rows.append([ds, part, ref, ds, f"{t.amount:.2f}", "", f"{bal:.2f}"])

    _write_csv(
        path,
        ["Tran Date", "Particulars", "Chq/Ref Number", "Value Date", "Withdrawal", "Deposit", "Closing Balance"],
        rows,
        header_lines=[
            f"Axis Bank - Savings Account Statement",
            f"Name: {p.full_name}",
            f"A/C No: XXXX{p.account_suffix}",
            f"Home Branch: {p.city}",
            "",
        ],
    )


def write_sbi(path: Path, p: Persona, txns: list[Txn]) -> None:
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    bal = 120_000.0
    refn = int(f"1{p.rng_seed}"[:9])
    rows: list[list[str]] = []
    for t in txns:
        ref = str(refn)
        refn += 1
        dstr = f"{t.d.day:02d} {months[t.d.month - 1]} {t.d.year}"
        if t.kind == "credit":
            desc = f"NEFT CR-{p.employer}-SALARY-{ref}"
            bal += t.amount
            rows.append([dstr, dstr, desc, ref, "", f"{t.amount:.2f}", f"{bal:.2f}"])
        else:
            if "Rent" in t.desc:
                desc = f"NEFT DR-RENT {p.city}-{ref}"
            elif "EMI" in t.desc:
                desc = f"ACH DR {t.desc}-{ref}"
            else:
                desc = f"UPI/{ref[-12:]}/{t.desc[:35]}/Payment"
            bal -= t.amount
            rows.append([dstr, dstr, desc, ref, f"{t.amount:.2f}", "", f"{bal:.2f}"])

    _write_csv(
        path,
        ["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Debit", "Credit", "Balance"],
        rows,
        header_lines=[
            f"State Bank of India - Account Statement",
            f"Account Name: {p.full_name}",
            f"Account Number: XXXX{p.account_suffix}",
            f"Branch: {p.city}",
            "",
        ],
    )


WRITERS: dict[BankFmt, Callable[[Path, Persona, list[Txn]], None]] = {
    "hdfc": write_hdfc,
    "icici": write_icici,
    "axis": write_axis,
    "sbi": write_sbi,
}


def _write_csv(
    path: Path,
    header: list[str],
    rows: list[list[str]],
    header_lines: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        for line in header_lines:
            f.write(line + "\n")
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: list[str] = []

    for p in PERSONAS:
        txns = build_persona_txns(p)
        fname = f"{p.bank_fmt.upper()}_{p.key.upper()}_ONBOARDING_STATEMENT_{p.full_name.replace(' ', '_')}.csv"
        out = OUT_DIR / fname
        WRITERS[p.bank_fmt](out, p, txns)
        debits = sum(t.amount for t in txns if t.kind == "debit")
        credits = sum(t.amount for t in txns if t.kind == "credit")
        summary.append(
            f"{fname}: {len(txns)} txns | salary INR {p.salary:,.0f}/mo | "
            f"credits INR {credits:,.0f} | debits INR {debits:,.0f} | pattern~{p.key}"
        )
        print(f"Wrote {out} ({len(txns)} transactions)")

    readme = OUT_DIR / "README_ONBOARDING_UPLOADS.md"
    readme.write_text(
        """# Team onboarding bank statements (upload demo)

**For new signups only** — does not modify `vikram@smartspend.in`, `priya@`, `rahul@`, `ananya@`, or `karan@` database seed data.

## Files

| Person | File | Bank | Monthly salary (pattern) |
|--------|------|------|--------------------------|
| Chirag Solanki | `HDFC_CHIRAG_...csv` | HDFC | ₹92,000 (like Vikram) |
| Amruta Abhangrao | `ICICI_AMRUTA_...csv` | ICICI | ₹75,000 (like Priya) |
| Sumit Dabas | `AXIS_SUMIT_...csv` | Axis | ₹45,000 (like Rahul) |
| Ganesh Patil | `SBI_GANESH_...csv` | SBI | ₹1,40,000 (like Ananya) |

Period: **Feb 2026 – 14 May 2026** (~170–200 transactions each).

## How to demo (Path B onboarding)

1. Sign up with a **new email** (not the pre-seeded demo accounts).
2. Source Selection → **Upload Bank Statement**.
3. Pick the CSV for that persona; institution name = bank from table above.
4. Wait for extraction → Dashboard.

## Regenerate

```bash
python backend/scripts/generate_team_onboarding_statements.py
```
""",
        encoding="utf-8",
    )
    print("\n--- Summary ---")
    for line in summary:
        print(line)
    print(f"\nREADME: {readme}")


if __name__ == "__main__":
    main()
