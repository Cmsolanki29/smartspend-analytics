#!/usr/bin/env python3
"""
Generate HDFC bank statement (CSV + PDF) for Vijay Kumar — ~400 transactions.

Realistic salaried Mumbai profile: stable monthly salary, rent + EMIs, SIP savings,
moderate UPI spend, plus fraud/dark-pattern rows for QA (never trimmed).

Regenerate overwrites:
  test samples/onboarding/HDFC_VIJAY_ONBOARDING_STATEMENT_Vijay_Kumar.{csv,pdf}

Run from repo root:
  python backend/scripts/generate_vijay_onboarding_statement.py
"""
from __future__ import annotations

import csv
import random
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "test samples" / "onboarding"

PERIOD_START = date(2025, 2, 1)
PERIOD_END = date(2026, 5, 14)
TARGET_TXNS = 400

VIJAY = {
    "full_name": "Vijay Kumar",
    "salary": 85_000.0,
    "rent": 22_000.0,
    "sip_monthly": 12_000.0,
    "fd_quarterly": 8_000.0,
    "annual_bonus": 45_000.0,
    "city": "Mumbai",
    "employer": "TATA CONSULTANCY SERVICES LTD",
    "account_suffix": "5587",
    "opening_balance": 118_000.0,
    "rng_seed": 558701,
}


@dataclass
class Txn:
    d: date
    kind: str  # credit | debit
    amount: float
    desc: str
    protected: bool = False


def _month_range() -> list[tuple[int, int, int]]:
    """(year, month, last_day) from PERIOD_START through PERIOD_END."""
    out: list[tuple[int, int, int]] = []
    y, m = PERIOD_START.year, PERIOD_START.month
    while (y, m) <= (PERIOD_END.year, PERIOD_END.month):
        if (y, m) == (PERIOD_END.year, PERIOD_END.month):
            last = PERIOD_END.day
        else:
            last = 28
        out.append((y, m, last))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _ml(y: int, m: int) -> str:
    return date(y, m, 1).strftime("%b").upper()[:3] + str(y)[-2:]


def _is_showcase_desc(desc: str) -> bool:
    u = desc.upper()
    keys = (
        "DUPLICATE",
        "TRIAL",
        "SCAM",
        "CRYPTO",
        "VELOCITY",
        "UNKNOWN",
        "MICRO AUTH",
        "INFLATED",
        "PHANTOM",
        "0247",
        "0312",
        "0420",
        "COLLECT",
        "COUNTERFEIT",
        "DORMANT",
        "HIDDEN",
        "LOTTERY",
        "TECH SUPPORT",
        "GAMING_TOPUP",
        "QUICKLOAN",
    )
    return any(k in u for k in keys)


def _is_protected(t: Txn) -> bool:
    if t.protected:
        return True
    if _is_showcase_desc(t.desc):
        return True
    u = t.desc.upper()
    if t.kind == "credit":
        return "SALARY" in u or "BONUS" in u
    if "RENT" in u or "EMI" in u or "SIP" in u or "FD" in u or "MUTUAL FUND" in u:
        return True
    for label in ("MSEDCL", "AIRTEL BROADBAND", "JIO POSTPAID"):
        if label in u:
            return True
    for label in ("NETFLIX STANDARD", "SPOTIFY FAMILY"):
        if label in u:
            return True
    return False


def _trim_to_target(txns: list[Txn], target: int) -> list[Txn]:
    """Keep salary, rent, EMIs, savings, utilities, showcase; subsample only discretionary UPI."""
    protected = [t for t in txns if _is_protected(t)]
    discretionary = [t for t in txns if not _is_protected(t)]
    need_disc = max(0, target - len(protected))
    if len(discretionary) <= need_disc:
        out = protected + discretionary
    else:
        rng = random.Random(VIJAY["rng_seed"] + 99)
        rng.shuffle(discretionary)
        discretionary = sorted(discretionary[:need_disc], key=lambda t: (t.d, t.kind, t.amount))
        out = protected + discretionary
    out.sort(key=lambda t: (t.d, 0 if t.kind == "credit" else 1, t.amount))
    return out


def build_vijay_txns() -> list[Txn]:
    rng = random.Random(VIJAY["rng_seed"])
    p = VIJAY
    txns: list[Txn] = []

    food = [("Swiggy", 220, 420), ("Zomato", 250, 480), ("EatSure", 180, 360)]
    transport = [
        ("Uber", 95, 280),
        ("Ola Cabs", 85, 260),
        ("Mumbai Local", 180, 180),
        ("Auto Rickshaw", 50, 95),
    ]
    grocery = [("BigBasket", 900, 1800), ("DMart Andheri", 800, 1600), ("Zepto", 650, 1200)]
    shop = [("Amazon", 500, 2200), ("Flipkart", 450, 1800), ("Myntra", 600, 2400)]
    petrol = [("HP Petrol Andheri", 1400, 2000)]

    emis = [
        (5, 14_200, "EMI HDFC Home Loan"),
        (5, 5_800, "EMI ICICI Car Loan"),
    ]
    subs = [
        (6, 649, "Netflix Standard"),
        (14, 179, "Spotify Family"),
        (7, 599, "Jio Postpaid Recharge"),
    ]
    utilities = [
        (3, 1_680, "MSEDCL Electricity Mumbai"),
        (4, 899, "Airtel Broadband"),
    ]

    for y, m, last_day in _month_range():
        ml = _ml(y, m)

        txns.append(
            Txn(
                date(y, m, 1),
                "credit",
                p["salary"],
                f"Salary Credit - Vijay Kumar - {ml}",
                protected=True,
            )
        )

        if last_day >= 2:
            txns.append(
                Txn(
                    date(y, m, 2),
                    "debit",
                    p["rent"],
                    f"Monthly Rent Andheri West - {ml}",
                    protected=True,
                )
            )

        for day, amt, label in utilities:
            if day <= last_day:
                txns.append(Txn(date(y, m, day), "debit", amt, label, protected=True))

        for day, amt, label in emis:
            if day <= last_day:
                txns.append(
                    Txn(
                        date(y, m, day),
                        "debit",
                        amt,
                        f"{label} - HDFC Bank AutoDebit",
                        protected=True,
                    )
                )

        for day, amt, label in subs:
            if day <= last_day:
                txns.append(Txn(date(y, m, day), "debit", amt, label, protected=True))

        if last_day >= 10:
            txns.append(
                Txn(
                    date(y, m, 10),
                    "debit",
                    p["sip_monthly"],
                    "ACH DR Axis Liquid Fund SIP Vijay Kumar",
                    protected=True,
                )
            )

        if m in (1, 4, 7, 10) and last_day >= 25:
            txns.append(
                Txn(
                    date(y, m, 25),
                    "debit",
                    p["fd_quarterly"],
                    "NEFT DR Self Transfer FD A/C XXXX9921 HDFC Bank",
                    protected=True,
                )
            )

        if m == 3 and last_day >= 28:
            txns.append(
                Txn(
                    date(y, m, 28),
                    "credit",
                    p["annual_bonus"],
                    f"NEFT CR TCS Annual Performance Bonus - {ml}",
                    protected=True,
                )
            )

        # Moderate discretionary (~8–12 debits/month)
        for day in range(3, last_day + 1):
            if day % 5 == 0:
                merch, lo, hi = rng.choice(food)
                txns.append(
                    Txn(
                        date(y, m, day),
                        "debit",
                        float(rng.randint(lo, hi)),
                        f"UPI {merch} Food Order Mumbai",
                    )
                )
            if day % 7 == 2:
                merch, lo, hi = rng.choice(transport)
                txns.append(
                    Txn(
                        date(y, m, day),
                        "debit",
                        float(rng.randint(lo, hi)),
                        f"UPI {merch} Mumbai",
                    )
                )
            if day % 11 == 4:
                merch, lo, hi = rng.choice(grocery)
                txns.append(
                    Txn(
                        date(y, m, day),
                        "debit",
                        float(rng.randint(lo, hi)),
                        f"UPI {merch} Grocery",
                    )
                )
            if day % 14 == 9:
                merch, lo, hi = rng.choice(shop)
                txns.append(
                    Txn(
                        date(y, m, day),
                        "debit",
                        float(rng.randint(lo, hi)),
                        f"UPI {merch} Shopping",
                    )
                )
            if day == 20 and day <= last_day:
                merch, lo, hi = rng.choice(petrol)
                txns.append(
                    Txn(date(y, m, day), "debit", float(rng.randint(lo, hi)), f"UPI {merch}")
                )

    showcase = [
        Txn(date(2026, 1, 8), "debit", 25_000, "IMPS DR Groww Unknown Device Bengaluru 0247 hrs"),
        Txn(date(2026, 2, 14), "debit", 18_500, "IMPS DR unknown7839201@paytm Night Transfer 0312 hrs"),
        Txn(date(2026, 4, 12), "debit", 28_500, "UPI CRYPTOX EXCHANGE DUBAI cryptox@ybl YESBANK"),
        Txn(date(2026, 5, 2), "debit", 12_000, "UPI QuickLoan App instant loan repayment quickloan@ybl"),
        Txn(date(2026, 5, 11), "debit", 8_333, "UPI IMPS Unknown UPI Velocity 1 of 3"),
        Txn(date(2026, 5, 11), "debit", 8_333, "UPI IMPS Unknown UPI Velocity 2 of 3"),
        Txn(date(2026, 5, 11), "debit", 8_334, "UPI IMPS Unknown UPI Velocity 3 of 3"),
        Txn(date(2026, 4, 3), "debit", 4_500, "UPI Unknown Merchant Jaipur QR geo anomaly Mumbai user"),
        Txn(date(2026, 3, 18), "debit", 9_999, "UPI Unknown_UPI_7839201@paytm transfer"),
        Txn(date(2026, 5, 7), "debit", 5_500, "UPI Gaming_TopUp_Unknown gametopup@paytm 0420 hrs"),
        Txn(date(2025, 12, 8), "debit", 3_000, "UPI Google Pay Tech Support Microsoft Scam pay@ybl"),
        Txn(date(2026, 4, 28), "debit", 2_200, "UPI Lucky Draw Prize Claim Advance Fee scam@paytm"),
        Txn(date(2026, 2, 21), "debit", 9_500, "UPI CryptoXchange Deposit urgent cryptox@ybl"),
        Txn(date(2026, 2, 3), "debit", 1.0, "UPI Apple com bill Card Verification Micro Auth"),
        Txn(date(2026, 2, 3), "debit", 499.0, "UPI SecureVPN Pro Trial Auto Convert pay@ybl"),
        Txn(date(2026, 2, 4), "debit", 2.0, "UPI Spotify trial verify charge"),
        Txn(date(2026, 2, 5), "debit", 199.0, "UPI Spotify Premium renewal after trial"),
        Txn(date(2026, 3, 15), "debit", 649, "UPI Netflix India Subscription Mumbai"),
        Txn(date(2026, 3, 15), "debit", 649, "UPI Netflix India DUPLICATE CHARGE same day"),
        Txn(date(2026, 3, 16), "debit", 649, "UPI Netflix India DUPLICATE CHARGE retry"),
        Txn(date(2026, 3, 22), "debit", 6_200, "UPI Swiggy Genie Corporate Inflated Invoice Mumbai"),
        Txn(date(2026, 4, 6), "debit", 1.0, "UPI Amazon Prime trial verify"),
        Txn(date(2026, 4, 7), "debit", 125.0, "UPI Amazon Prime monthly after free trial"),
        Txn(date(2026, 4, 19), "debit", 2998, "UPI Netflix double charge device session 2"),
        Txn(date(2026, 5, 9), "debit", 1_299, "UPI Meesho Seller Phantom Deal 95pct off pay@ybl"),
        Txn(date(2026, 5, 10), "debit", 399, "UPI Hotstar Premium post IPL dormant renewal"),
        Txn(date(2026, 5, 12), "debit", 199, "UPI Nykaa Pink Membership hidden auto renew"),
        Txn(date(2026, 5, 13), "debit", 1_499, "UPI Swiggy Super Annual negative savings trap"),
        Txn(date(2026, 5, 8), "debit", 999, "UPI LinkedIn Premium dormant renewal"),
        Txn(date(2026, 4, 25), "debit", 75, "UPI iCloud Plus 200GB hidden upgrade iOS"),
        Txn(date(2026, 3, 8), "debit", 1499, "UPI Flipkart Seller counterfeit iPhone 3499"),
        Txn(date(2026, 2, 28), "debit", 5000, "UPI CRED credit card bill payment collect request"),
        Txn(date(2026, 5, 6), "debit", 299, "UPI Hotstar duplicate booking same match"),
        Txn(date(2026, 5, 6), "debit", 299, "UPI Hotstar duplicate booking session 2"),
        Txn(date(2026, 4, 14), "debit", 199, "UPI JioSaavn Pro price hike renewal"),
        Txn(date(2026, 3, 25), "debit", 49, "UPI Zepto Pass auto renew low usage"),
    ]
    txns.extend(showcase)

    return _trim_to_target(txns, TARGET_TXNS)


def _simulate_closing(txns: list[Txn]) -> float:
    bal = VIJAY["opening_balance"]
    for t in sorted(txns, key=lambda x: (x.d, 0 if x.kind == "credit" else 1)):
        if t.kind == "credit":
            bal += t.amount
        else:
            bal -= t.amount
    return bal


def write_hdfc_csv(path: Path, txns: list[Txn]) -> None:
    p = VIJAY
    bal = p["opening_balance"]
    refn = 5587001
    rows: list[list[str]] = []

    for t in txns:
        ref = f"N{refn}"
        refn += 1
        vd = t.d.strftime("%d/%m/%y")
        if t.kind == "credit":
            if "Salary" in t.desc:
                nar = f"NEFT-HDFC0001234-{p['employer']}-SALARY {_ml(t.d.year, t.d.month)}-{ref}"
            elif "Bonus" in t.desc:
                nar = f"NEFT CR-{p['employer']}-BONUS {_ml(t.d.year, t.d.month)}-{ref[-6:]}"
            else:
                nar = f"NEFT CR-{t.desc[:80]}-{ref[-6:]}"
            bal += t.amount
            rows.append([vd, nar, ref, vd, "", f"{t.amount:.2f}", f"{bal:.2f}"])
        else:
            if "Rent" in t.desc:
                nar = f"NEFT DR-SBIN0012345-LANDLORD RENT {_ml(t.d.year, t.d.month)}-{ref[-9:]}"
            elif "EMI" in t.desc:
                nar = f"ACH DR-{t.desc.upper()}-{ref[-9:]}"
            elif "SIP" in t.desc or "FD" in t.desc:
                nar = t.desc.replace(" ", "-")[:100] + f"-{ref[-6:]}"
            elif "IMPS" in t.desc:
                nar = t.desc.replace(" ", "-")[:100] + f"-{ref[-6:]}"
            elif "UPI" in t.desc:
                nar = t.desc.replace(" ", "-")[:100] + f"-{ref[-6:]}"
            else:
                nar = f"UPI-{t.desc[:40]}-pay@ybl-PAYTMBANK-{ref[-6:]}"
            bal -= t.amount
            rows.append([vd, nar, ref, vd, f"{t.amount:.2f}", "", f"{bal:.2f}"])

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write("HDFC BANK - Account Statement\n")
        f.write(f"Account Holder : {p['full_name']}\n")
        f.write(f"Account No     : XXXX{p['account_suffix']}\n")
        f.write(f"Branch         : {p['city']}\n")
        f.write(
            f"Period         : {PERIOD_START.strftime('%d/%m/%Y')} to {PERIOD_END.strftime('%d/%m/%Y')}\n\n"
        )
        w = csv.writer(f)
        w.writerow(
            [
                "Date",
                "Narration",
                "Chq./Ref.No.",
                "Value Dt",
                "Withdrawal Amt.",
                "Deposit Amt.",
                "Closing Balance",
            ]
        )
        w.writerows(rows)


def write_hdfc_pdf(path: Path, txns: list[Txn]) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise SystemExit("Install reportlab: pip install reportlab") from exc

    p = VIJAY
    brand = colors.HexColor("#004C8F")
    bal = p["opening_balance"]
    refn = 5587001
    data_rows: list[list[str]] = []

    for t in txns:
        ref = f"N{refn}"
        refn += 1
        vd = t.d.strftime("%d/%m/%Y")
        if t.kind == "credit":
            if "Salary" in t.desc:
                nar = f"NEFT-HDFC0001234-{p['employer']}-SALARY"
            elif "Bonus" in t.desc:
                nar = "NEFT CR TCS Annual Performance Bonus"
            else:
                nar = t.desc[:90]
            bal += t.amount
            data_rows.append([vd, nar, ref, "", f"{t.amount:,.2f}", f"{bal:,.2f}"])
        else:
            if "Rent" in t.desc:
                nar = "NEFT DR LANDLORD RENT"
            elif "EMI" in t.desc:
                nar = f"ACH DR {t.desc[:55]}"
            elif "SIP" in t.desc:
                nar = "ACH DR Axis Liquid Fund SIP"
            elif "FD" in t.desc:
                nar = "NEFT DR Self FD Transfer"
            else:
                nar = t.desc[:95]
            bal -= t.amount
            data_rows.append([vd, nar, ref, f"{t.amount:,.2f}", "", f"{bal:,.2f}"])

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.4 * inch,
        title=f"HDFC Statement - {p['full_name']}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "T", parent=styles["Heading1"], fontSize=15, textColor=brand, alignment=TA_LEFT
    )
    sub_style = ParagraphStyle("S", parent=styles["Normal"], fontSize=8, leading=11)
    small = ParagraphStyle("Sm", parent=styles["Normal"], fontSize=6, leading=8)

    story = [
        Paragraph("<b>HDFC Bank</b> — Savings Account Statement", title_style),
        Spacer(1, 5),
        Paragraph(
            f"<b>Account Holder:</b> {p['full_name']}<br/>"
            f"<b>Account Number:</b> XXXX{p['account_suffix']} &nbsp; <b>Branch:</b> {p['city']}<br/>"
            f"<b>Period:</b> {PERIOD_START.strftime('%d %b %Y')} – {PERIOD_END.strftime('%d %b %Y')}<br/>"
            f"<b>Monthly Salary:</b> INR {p['salary']:,.0f} &nbsp; "
            f"<b>Monthly SIP:</b> INR {p['sip_monthly']:,.0f} &nbsp; "
            f"<b>Transactions:</b> {len(txns)}",
            sub_style,
        ),
        Spacer(1, 8),
    ]

    header = ["Date", "Narration", "Ref", "Withdrawal (INR)", "Deposit (INR)", "Balance (INR)"]
    table_data = [header]
    for row in data_rows:
        table_data.append(
            [
                row[0],
                Paragraph(row[1].replace("&", "&amp;"), small),
                row[2],
                row[3],
                row[4],
                row[5],
            ]
        )

    tbl = Table(
        table_data,
        colWidths=[0.8 * inch, 4.0 * inch, 0.7 * inch, 0.95 * inch, 0.95 * inch, 1.0 * inch],
        repeatRows=1,
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), brand),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 6),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#CCCCCC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(tbl)
    doc.build(story)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    txns = build_vijay_txns()
    base = "HDFC_VIJAY_ONBOARDING_STATEMENT_Vijay_Kumar"
    csv_path = OUT_DIR / f"{base}.csv"
    pdf_path = OUT_DIR / f"{base}.pdf"

    write_hdfc_csv(csv_path, txns)
    print(f"Wrote {csv_path} ({len(txns)} transactions)")

    try:
        write_hdfc_pdf(pdf_path, txns)
        print(f"Wrote {pdf_path} ({len(txns)} transactions)")
    except SystemExit:
        print("PDF skipped — pip install reportlab")
    except Exception as exc:
        print(f"PDF failed: {exc}")

    debits = sum(t.amount for t in txns if t.kind == "debit")
    credits = sum(t.amount for t in txns if t.kind == "credit")
    salaries = sum(1 for t in txns if "Salary" in t.desc)
    showcase_n = sum(1 for t in txns if _is_showcase_desc(t.desc))
    savings_n = sum(1 for t in txns if "SIP" in t.desc or "FD" in t.desc)
    closing = _simulate_closing(txns)
    print(
        f"\nVijay Kumar | {len(txns)} txns | {salaries} salary credits | "
        f"{savings_n} savings (SIP/FD) | ~{showcase_n} fraud/dark rows"
    )
    print(
        f"Salary INR {VIJAY['salary']:,.0f}/mo | rent INR {VIJAY['rent']:,.0f} | "
        f"SIP INR {VIJAY['sip_monthly']:,.0f}/mo | credits INR {credits:,.0f} | "
        f"debits INR {debits:,.0f} | closing balance INR {closing:,.0f}"
    )
    print(f"Period: {PERIOD_START} to {PERIOD_END}")


if __name__ == "__main__":
    main()
