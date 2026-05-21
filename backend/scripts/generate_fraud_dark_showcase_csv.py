"""
Generate HDFC CSV: ~50 days, ALL FraudShield + Dark Pattern showcase rows in that window.

Output: test samples/onboarding/HDFC_FRAUD_DARK_SHOWCASE_QA.csv

Run: python backend/scripts/generate_fraud_dark_showcase_csv.py
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "test samples" / "onboarding" / "HDFC_FRAUD_DARK_SHOWCASE_QA.csv"

# 50-day window (Mar 1 – Apr 19, 2026). Use Transactions month = Mar OR Apr.
PERIOD_START = date(2026, 3, 1)
PERIOD_END = PERIOD_START + timedelta(days=49)
OPENING = 280_000.0
SALARY = 85_000.0
RENT = 22_000.0


@dataclass
class Row:
    d: date
    desc: str
    kind: str  # credit | debit
    amount: float


def _d(day: int) -> date:
    """Day offset 1..50 from PERIOD_START."""
    return PERIOD_START + timedelta(days=day - 1)


def _ml(y: int, m: int) -> str:
    return date(y, m, 1).strftime("%b%y").upper()


def _baseline() -> list[Row]:
    """Light normal spend so dashboard stays sane (~12 rows)."""
    return [
        Row(_d(1), "Salary March TCS", "credit", SALARY),
        Row(_d(2), "Rent March", "debit", RENT),
        Row(_d(4), "UPI MSEDCL Electricity Mumbai", "debit", 1680),
        Row(_d(6), "ACH DR Axis Liquid Fund SIP Vijay Kumar", "debit", 12_000),
        Row(_d(8), "UPI BigBasket Grocery", "debit", 1240),
        Row(_d(12), "UPI Swiggy Food Order Mumbai", "debit", 385),
        Row(_d(18), "UPI Zepto Grocery", "debit", 890),
        Row(_d(22), "UPI Ola Cabs Mumbai", "debit", 245),
        Row(_d(28), "UPI Amazon Shopping", "debit", 1560),
        Row(_d(32), "Salary April TCS", "credit", SALARY),
        Row(_d(33), "Rent April", "debit", RENT),
        Row(_d(40), "UPI Jio Postpaid Recharge", "debit", 599),
    ]


def _showcase() -> list[Row]:
    """
    ~58 showcase debits inside 50 days — tuned for dark_patterns.py + FraudShield rules.
    Day numbers are 1..50 relative to PERIOD_START.
    """
    s: list[Row] = []

    # --- EK_RUPEE / micro-auth + FREE_TRIAL (trial day T, follow-up T+18..30) ---
    s += [
        Row(_d(3), "UPI Apple com bill Card Verification Micro Auth", "debit", 1.0),
        Row(_d(22), "UPI SecureVPN Pro Trial Auto Convert pay@ybl", "debit", 499.0),
        Row(_d(4), "UPI Google Play trial verify charge", "debit", 2.0),
        Row(_d(26), "UPI Google Play Premium renewal after trial", "debit", 199.0),
        Row(_d(5), "UPI Spotify trial verify charge", "debit", 2.0),
        Row(_d(24), "UPI Spotify Premium renewal after trial", "debit", 199.0),
        Row(_d(6), "UPI YouTube Premium trial verify", "debit", 1.0),
        Row(_d(28), "UPI YouTube Premium monthly renewal", "debit", 299.0),
        Row(_d(7), "UPI OpenAI ChatGPT trial verify micro auth", "debit", 1.0),
        Row(_d(30), "UPI OpenAI Plus subscription renewal", "debit", 1999.0),
        Row(_d(9), "UPI Amazon Prime trial verify", "debit", 1.0),
        Row(_d(27), "UPI Amazon Prime monthly after free trial", "debit", 125.0),
        Row(_d(10), "UPI Hotstar Premium trial verify micro auth", "debit", 1.0),
        Row(_d(29), "UPI Hotstar Premium IPL renewal", "debit", 399.0),
        Row(_d(11), "UPI Netflix India trial verify", "debit", 1.0),
        Row(_d(31), "UPI Netflix India Subscription Mumbai", "debit", 649.0),
        Row(_d(14), "UPI Netflix com bill micro auth verify", "debit", 1.0),
        Row(_d(16), "UPI Prime Video trial verify micro auth", "debit", 1.0),
        Row(_d(20), "UPI Canva Pro trial verify micro auth", "debit", 1.0),
    ]

    # --- DUPLICATE_CHARGE (same day, same amount) ---
    s += [
        Row(_d(13), "UPI Netflix India DUPLICATE CHARGE same day", "debit", 649.0),
        Row(_d(13), "UPI Netflix India DUPLICATE CHARGE retry", "debit", 649.0),
        Row(_d(17), "UPI Swiggy Instamart DUPLICATE same day", "debit", 420.0),
        Row(_d(17), "UPI Swiggy Instamart DUPLICATE retry", "debit", 420.0),
        Row(_d(21), "UPI Hotstar duplicate booking same match", "debit", 299.0),
        Row(_d(21), "UPI Hotstar duplicate booking session 2", "debit", 299.0),
        Row(_d(15), "UPI Spotify Premium DUPLICATE same day", "debit", 199.0),
        Row(_d(15), "UPI Spotify Premium DUPLICATE retry", "debit", 199.0),
        Row(_d(35), "UPI Zomato Gold DUPLICATE same day", "debit", 349.0),
        Row(_d(35), "UPI Zomato Gold DUPLICATE retry", "debit", 349.0),
        Row(_d(42), "UPI Paytm Movies DUPLICATE same day", "debit", 550.0),
        Row(_d(42), "UPI Paytm Movies DUPLICATE retry", "debit", 550.0),
    ]

    # --- PRICE_INCREASE (3 increasing recurring, same merchant) ---
    s += [
        Row(_d(8), "UPI LinkedIn Premium dormant renewal", "debit", 799.0),
        Row(_d(23), "UPI LinkedIn Premium price hike renewal", "debit", 899.0),
        Row(_d(38), "UPI LinkedIn Premium hidden auto renew", "debit", 999.0),
        Row(_d(10), "UPI SecureVPN Pro monthly plan", "debit", 199.0),
        Row(_d(25), "UPI SecureVPN Pro monthly plan", "debit", 249.0),
        Row(_d(40), "UPI SecureVPN Pro monthly plan", "debit", 299.0),
    ]

    # --- ESCALATING (unknown/trading/kyc) ---
    s += [
        Row(_d(19), "UPI Unknown Trading KYC Verify step1", "debit", 1.0),
        Row(_d(20), "UPI Unknown Trading KYC Verify step2", "debit", 5.0),
        Row(_d(22), "UPI Unknown Trading KYC Verify step3", "debit", 500.0),
        Row(_d(24), "UPI Unknown Trading KYC Verify step4", "debit", 5000.0),
    ]

    # --- FraudShield: crypto / scam / unknown / large ---
    s += [
        Row(_d(5), "IMPS DR Groww Unknown Device Bengaluru 0247 hrs", "debit", 25_000.0),
        Row(_d(7), "IMPS DR unknown7839201@paytm Night Transfer 0312 hrs", "debit", 18_500.0),
        Row(_d(12), "UPI CryptoXchange Deposit urgent cryptox@ybl", "debit", 9_500.0),
        Row(_d(34), "UPI CRYPTOX EXCHANGE DUBAI cryptox@ybl international", "debit", 28_500.0),
        Row(_d(36), "UPI Lucky Draw Prize Claim Advance Fee scam@paytm", "debit", 2_200.0),
        Row(_d(18), "UPI Unknown_UPI_7839201@paytm transfer", "debit", 9_999.0),
        Row(_d(26), "UPI Unknown Merchant Jaipur QR geo anomaly", "debit", 4_500.0),
        Row(_d(37), "UPI QuickLoan App instant loan repayment quickloan@ybl", "debit", 12_000.0),
        Row(_d(39), "UPI Gaming_TopUp_Unknown gametopup@paytm 0420 hrs", "debit", 5_500.0),
        Row(_d(14), "UPI Google Pay Tech Support Microsoft Scam pay@ybl", "debit", 3_000.0),
        Row(_d(41), "UPI Meesho Seller Phantom Deal 95pct off", "debit", 1_299.0),
        Row(_d(43), "UPI Nykaa Pink Membership hidden auto renew", "debit", 399.0),
        Row(_d(44), "UPI Swiggy Super Annual negative savings trap", "debit", 1_499.0),
        Row(_d(16), "UPI Flipkart Seller counterfeit iPhone listing", "debit", 1_499.0),
        Row(_d(27), "UPI Swiggy Genie Corporate Inflated Invoice Mumbai", "debit", 6_200.0),
        Row(_d(33), "UPI Netflix double charge device session 2", "debit", 2998.0),
        Row(_d(45), "UPI iCloud Plus 200GB hidden upgrade iOS", "debit", 75.0),
        Row(_d(46), "UPI Zepto Pass auto renew low usage", "debit", 49.0),
        Row(_d(30), "UPI CRED credit card bill payment collect request", "debit", 5000.0),
        Row(_d(32), "UPI JioSaavn Pro price hike renewal", "debit", 199.0),
    ]

    # --- Velocity burst (same day) ---
    s += [
        Row(_d(47), "UPI IMPS Unknown UPI Velocity 1 of 3", "debit", 8_333.0),
        Row(_d(47), "UPI IMPS Unknown UPI Velocity 2 of 3", "debit", 8_333.0),
        Row(_d(47), "UPI IMPS Unknown UPI Velocity 3 of 3", "debit", 8_334.0),
    ]

    # --- Extra micro-auth (import heuristic) ---
    s += [
        Row(_d(2), "UPI Apple com bill verify micro auth", "debit", 1.0),
        Row(_d(48), "UPI Microsoft 365 trial verify micro auth", "debit", 1.0),
        Row(_d(49), "UPI Adobe Creative trial verify micro auth", "debit", 1.0),
        Row(_d(50), "UPI Disney Plus Hotstar trial verify", "debit", 1.0),
    ]

    return s


def _write_csv(path: Path, rows: list[Row]) -> None:
    rows = sorted(rows, key=lambda r: (r.d, 0 if r.kind == "credit" else 1))
    bal = OPENING
    refn = 9900001
    data: list[list[str]] = []

    for t in rows:
        ref = f"N{refn}"
        refn += 1
        vd = t.d.strftime("%d/%m/%y")
        if t.kind == "credit":
            if "Salary" in t.desc:
                nar = f"NEFT-HDFC0001234-TATA CONSULTANCY SERVICES LTD-SALARY {_ml(t.d.year, t.d.month)}-{ref}"
            else:
                nar = f"NEFT CR-{t.desc[:60]}-{ref[-6:]}"
            bal += t.amount
            data.append([vd, nar, ref, vd, "", f"{t.amount:.2f}", f"{bal:.2f}"])
        else:
            if "Rent" in t.desc:
                nar = f"NEFT DR-SBIN0012345-LANDLORD RENT {_ml(t.d.year, t.d.month)}-{ref[-9:]}"
            elif "IMPS" in t.desc:
                nar = t.desc.replace(" ", "-")[:100] + f"-{ref[-6:]}"
            elif "ACH" in t.desc:
                nar = t.desc.replace(" ", "-")[:100] + f"-{ref[-6:]}"
            else:
                nar = t.desc.replace(" ", "-")[:100] + f"-{ref[-6:]}"
            bal -= t.amount
            data.append([vd, nar, ref, vd, f"{t.amount:.2f}", "", f"{bal:.2f}"])

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write("HDFC BANK - Account Statement\n")
        f.write("Account Holder : Demo QA Fraud Dark Showcase\n")
        f.write("Account No     : XXXX9900\n")
        f.write("Branch         : Mumbai\n")
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
        w.writerows(data)

    days = (PERIOD_END - PERIOD_START).days + 1
    print(f"Wrote {path}")
    print(f"  Window: {PERIOD_START} .. {PERIOD_END} ({days} days)")
    print(f"  Total rows: {len(rows)} (baseline {len(_baseline())}, showcase {len(_showcase())})")
    print(f"  Closing balance: {bal:,.2f}")


def main() -> None:
    _write_csv(OUT, _baseline() + _showcase())


if __name__ == "__main__":
    main()
