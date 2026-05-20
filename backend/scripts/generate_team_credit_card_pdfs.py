#!/usr/bin/env python3
"""
Generate 6-month credit card statement PDFs for Chirag Solanki and Amruta Abhangrao.

~90–110 card purchases each: flights, hotels, trains, EMIs, ChatGPT, subs, food, shopping.

Run from repo root:
  python backend/scripts/generate_team_credit_card_pdfs.py
"""
from __future__ import annotations

import calendar
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "test samples" / "credit_card"

# 6-month statement window (upload / parser friendly)
PERIOD_START = date(2025, 12, 1)
PERIOD_END = date(2026, 5, 14)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError as exc:
    raise SystemExit("Install reportlab: pip install reportlab") from exc

# Helvetica cannot render ₹ (U+20B9) — registers Windows Nirmala or falls back to "Rs."
_FONT_BODY = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_RUPEE_CHAR = "Rs."


def _register_statement_fonts() -> None:
    global _FONT_BODY, _FONT_BOLD, _RUPEE_CHAR
    win = Path(r"C:\Windows\Fonts")
    pairs = [
        (win / "NIRMALA.TTF", win / "NIRMALAB.TTF"),
        (win / "Nirmala.ttf", win / "NIRMALAB.TTF"),
        (win / "arial.ttf", win / "arialbd.ttf"),
    ]
    for regular, bold in pairs:
        if not regular.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont("StmtFont", str(regular)))
            _FONT_BODY = "StmtFont"
            if bold.is_file():
                pdfmetrics.registerFont(TTFont("StmtFont-Bold", str(bold)))
                _FONT_BOLD = "StmtFont-Bold"
            else:
                _FONT_BOLD = "StmtFont"
            _RUPEE_CHAR = "\u20b9"  # ₹ visible with Nirmala / Arial Unicode
            return
        except Exception:
            continue


_register_statement_fonts()


def _money(amount: float, *, prefix: bool = True) -> str:
    """Format amount with visible rupee (₹) or Rs. fallback."""
    sym = _RUPEE_CHAR
    num = f"{amount:,.2f}"
    return f"{sym} {num}" if prefix else num


@dataclass
class CcPersona:
    key: str
    full_name: str
    bank: str
    card_label: str
    card_last4: str
    city: str
    brand: colors.Color
    billing_start: date
    billing_end: date
    due_date: date
    credit_limit: int
    txns: list[tuple[date, str, float]]
    emi_plans: int


def _months_between(start: date, end: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _day_in_month(rng: random.Random, year: int, month: int, lo: int = 1, hi: int = 28) -> date:
    dim = calendar.monthrange(year, month)[1]
    d = rng.randint(lo, min(hi, dim))
    return date(year, month, d)


def _jitter(rng: random.Random, amount: float, pct: float = 0.08) -> float:
    delta = amount * rng.uniform(-pct, pct)
    return max(1.0, round(amount + delta, 2))


def _generate_txns(
    seed: int,
    city: str,
    *,
    profile: str,
) -> list[tuple[date, str, float]]:
    """Build ~6 months of credit-card debits (no salary — card spends only)."""
    rng = random.Random(seed)
    txns: list[tuple[date, str, float]] = []
    months = _months_between(PERIOD_START, PERIOD_END)

    def add(y: int, m: int, desc: str, amt: float, day: int | None = None) -> None:
        dim = calendar.monthrange(y, m)[1]
        d = min(day or rng.randint(1, dim), dim)
        txns.append((date(y, m, d), desc, _jitter(rng, amt)))

    if profile == "chirag":
        # ── Monthly EMIs on card (match bank stmt device EMIs) ──
        for y, m in months:
            add(y, m, "EMI IPHONE 15 PRO MAX - HDFC CC", 7083.00, 5)
            add(y, m, "EMI MACBOOK AIR M2 - HDFC CC", 8916.00, 5)

        # ── Subscriptions (fixed days) ──
        subs = [
            (8, "CHATGPT PLUS OPENAI", 1999.00),
            (8, "LINKEDIN PREMIUM", 999.00),
            (11, "CANVA PRO", 499.00),
            (14, "SPOTIFY INDIA", 119.00),
            (18, "YOUTUBE PREMIUM", 129.00),
            (20, "AMAZON PRIME VIDEO", 125.00),
            (22, "NOTION LABS INC", 800.00),
            (25, "GITHUB INC", 650.00),
            (27, "CURSOR AI PRO", 1800.00),
            (12, "MICROSOFT 365", 489.00),
            (15, "GOOGLE ONE STORAGE", 130.00),
        ]
        for y, m in months:
            for day, desc, amt in subs:
                add(y, m, desc, amt, day)

        # ── Travel: flights, hotels, trains (2–4 per month) ──
        flights = [
            ("INDIGO AIR Pune-Bengaluru", 4280.00),
            ("INDIGO AIR Bengaluru-Pune", 4150.00),
            ("AIR INDIA EXPRESS Pune-Delhi", 6890.00),
            ("AIR INDIA Delhi-Pune", 7120.00),
            ("MAKEMYTRIP FLIGHT BOOKING", 5420.00),
            ("GOIBIBO FLIGHT PUNE-MUMBAI", 2890.00),
        ]
        hotels = [
            ("OYO ROOMS PUNE FC ROAD", 1840.00),
            ("MARRIOTT PUNE CONFERENCE", 12450.00),
            ("TREEHOUSE HOTEL HINJEWADI", 3200.00),
            ("IBIS PUNE HINJEWADI", 4100.00),
            ("BOOKING.COM HOTEL STAY", 5600.00),
        ]
        trains = [
            ("IRCTC TICKET PUNE-MUMBAI", 1245.00),
            ("IRCTC TICKET MUMBAI-PUNE", 1180.00),
            ("IRCTC TATKAL PUNE-HYD", 1890.00),
            ("IRCTC CONFIRM PUNE-DELHI", 2450.00),
            ("CONFIRMTKT TRAIN BOOKING", 980.00),
        ]
        travel_pool = flights + hotels + trains
        for y, m in months:
            picks = rng.sample(travel_pool, k=rng.randint(3, 5))
            for desc, amt in picks:
                add(y, m, desc, amt)

        # ── Food & daily (8–12 per month) ──
        food = [
            ("SWIGGY PUNE", 420.0),
            ("ZOMATO ONLINE ORDER", 380.0),
            ("STARBUCKS PUNE", 525.0),
            ("DOMINOS PIZZA PUNE", 649.0),
            ("MCDONALDS INDIA", 320.0),
        ]
        for y, m in months:
            for _ in range(rng.randint(8, 12)):
                desc, amt = rng.choice(food)
                add(y, m, desc, amt)

        # ── Shopping & fuel ──
        shop = [
            ("AMAZON PAY INDIA", 2845.0),
            ("FLIPKART INTERNET", 1573.0),
            ("MYNTRA DESIGNS", 2155.0),
            ("RELIANCE DIGITAL PUNE", 3299.0),
            ("DMART READY PUNE", 1842.0),
            ("HPCL PETROL PUMP PUNE", 1650.0),
            ("CROMA PUNE", 8990.0),
            ("APPLE.COM/BILL", 299.0),
            ("PVR CINEMAS PUNE", 847.0),
            ("BOOKMYSHOW", 697.0),
            ("UBER INDIA", 267.0),
            ("OLA CABS PUNE", 312.0),
            ("APOLLO PHARMACY PUNE", 810.0),
        ]
        for y, m in months:
            for _ in range(rng.randint(5, 8)):
                desc, amt = rng.choice(shop)
                add(y, m, desc, amt)

    else:  # amruta
        for y, m in months:
            add(y, m, "EMI SONY WH1000XM5 HEADPHONE CC", 2499.00, 6)
            add(y, m, "EMI SAMSUNG GALAXY TAB - ICICI CC", 3200.00, 6)

        subs = [
            (7, "NETFLIX INDIA", 649.00),
            (7, "CHATGPT PLUS OPENAI", 1999.00),
            (9, "ZEPTO PASS", 49.00),
            (12, "SPOTIFY FAMILY", 179.00),
            (15, "AMAZON PRIME VIDEO", 125.00),
            (18, "HOTSTAR SUPER", 299.00),
            (22, "NYKAA PRO", 299.00),
            (25, "GOOGLE PLAY", 199.00),
            (28, "ADOBE CREATIVE CLOUD", 1675.00),
        ]
        for y, m in months:
            for day, desc, amt in subs:
                add(y, m, desc, amt, day)

        flights = [
            ("INDIGO AIR Mumbai-Goa", 3890.00),
            ("INDIGO AIR Goa-Mumbai", 3650.00),
            ("SPICEJET Mumbai-Bengaluru", 4200.00),
            ("AIR INDIA Mumbai-Delhi", 7850.00),
            ("MAKEMYTRIP FLIGHT BOOKING", 4980.00),
        ]
        hotels = [
            ("OYO ROOMS MUMBAI ANDHERI", 2100.00),
            ("FABHOTELS GOA CALANGUTE", 4500.00),
            ("Taj Vivanta Mumbai", 8900.00),
            ("BOOKING.COM HOTEL GOA", 6200.00),
            ("AGODA HOTEL MUMBAI", 3800.00),
        ]
        trains = [
            ("IRCTC TICKET MUMBAI-PUNE", 980.00),
            ("IRCTC TICKET PUNE-MUMBAI", 1020.00),
            ("IRCTC MUMBAI-NSK", 650.00),
            ("IRCTC TATKAL MUMBAI-AHM", 1650.00),
            ("CONFIRMTKT TRAIN BOOKING", 890.00),
        ]
        travel_pool = flights + hotels + trains
        for y, m in months:
            picks = rng.sample(travel_pool, k=rng.randint(3, 5))
            for desc, amt in picks:
                add(y, m, desc, amt)

        food = [
            ("SWIGGY MUMBAI", 313.0),
            ("ZOMATO ONLINE ORDER", 462.0),
            ("STARBUCKS MUMBAI", 495.0),
            ("BURGER KING MUMBAI", 380.0),
            ("AUTO RICKSHAW MUMBAI", 85.0),
        ]
        for y, m in months:
            for _ in range(rng.randint(8, 12)):
                desc, amt = rng.choice(food)
                add(y, m, desc, amt)

        shop = [
            ("AMAZON PAY INDIA", 2010.0),
            ("FLIPKART INTERNET", 1783.0),
            ("MYNTRA DESIGNS", 1859.0),
            ("BIGBASKET", 1124.0),
            ("DMART READY MUMBAI", 1567.0),
            ("DECATHLON INDIA", 2460.0),
            ("AJIO ONLINE", 1685.0),
            ("NYKAA ONLINE", 892.0),
            ("APOLLO PHARMACY MUMBAI", 1130.0),
            ("HPCL PETROL PUMP MUMBAI", 1420.0),
            ("UBER MUMBAI", 281.0),
            ("PVR CINEMAS MUMBAI", 641.0),
            ("BOOKMYSHOW", 697.0),
            ("LENSKART MUMBAI", 2400.0),
        ]
        for y, m in months:
            for _ in range(rng.randint(5, 8)):
                desc, amt = rng.choice(shop)
                add(y, m, desc, amt)

    # Dedupe same day + same merchant (keep higher amount)
    seen: dict[tuple[date, str], float] = {}
    for d, desc, amt in txns:
        key = (d, desc)
        seen[key] = max(seen.get(key, 0), amt)
    merged = [(d, desc, amt) for (d, desc), amt in seen.items()]
    merged.sort(key=lambda x: (x[0], x[1]))
    return merged


PERSONAS: tuple[CcPersona, ...] = (
    CcPersona(
        key="chirag",
        full_name="Chirag Solanki",
        bank="HDFC BANK",
        card_label="HDFC Regalia Credit Card",
        card_last4="9104",
        city="Pune",
        brand=colors.HexColor("#004C8F"),
        billing_start=PERIOD_START,
        billing_end=PERIOD_END,
        due_date=date(2026, 5, 28),
        credit_limit=350_000,
        txns=_generate_txns(92001, "Pune", profile="chirag"),
        emi_plans=2,
    ),
    CcPersona(
        key="amruta",
        full_name="Amruta Abhangrao",
        bank="ICICI BANK",
        card_label="ICICI Coral Credit Card",
        card_last4="7738",
        city="Mumbai",
        brand=colors.HexColor("#F58220"),
        billing_start=PERIOD_START,
        billing_end=PERIOD_END,
        due_date=date(2026, 5, 30),
        credit_limit=250_000,
        txns=_generate_txns(75002, "Mumbai", profile="amruta"),
        emi_plans=2,
    ),
)


def _fmt_date(d: date, bank: str) -> str:
    return d.strftime("%d-%b-%Y")


def _para_style(styles, name: str, **kw) -> ParagraphStyle:
    base = dict(parent=styles["Normal"], fontName=_FONT_BODY)
    base.update(kw)
    return ParagraphStyle(name, **base)


def _build_txn_table(p: CcPersona, styles) -> Table:
    small = _para_style(styles, "Cell", fontSize=7, leading=9)
    rows: list[list] = [["Date", "Description", "Amount (INR)"]]
    for d, desc, amt in sorted(p.txns, key=lambda x: x[0]):
        rows.append([
            _fmt_date(d, p.bank),
            Paragraph(desc.replace("&", "&amp;")[:80], small),
            _money(amt),
        ])
    col_widths = [1.05 * inch, 3.75 * inch, 1.15 * inch]
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), p.brand),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
                ("FONTNAME", (0, 1), (-1, -1), _FONT_BODY),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (2, 1), (2, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F8FC")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return tbl


def write_hdfc_style(path: Path, p: CcPersona) -> None:
    total = sum(a for _, _, a in p.txns)
    prev_bal = 18_600.0
    payments = 45_000.0
    finance = 890.0
    total_due = round(prev_bal - payments + total + finance, 2)
    min_due = round(total_due * 0.1, 2)
    avail = max(0, p.credit_limit - total_due)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.4 * inch,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "T", parent=styles["Heading1"], fontSize=14, textColor=p.brand, fontName=_FONT_BOLD
    )
    body = _para_style(styles, "B", fontSize=9, leading=12)
    small = _para_style(styles, "S", fontSize=7, leading=9)

    period = f"{p.billing_start.strftime('%d %b %Y')} - {p.billing_end.strftime('%d %b %Y')}"
    story = [
        Paragraph("<b>HDFC BANK CREDIT CARD STATEMENT</b>", title),
        Spacer(1, 6),
        Paragraph(
            f"<b>Customer Name</b> {p.full_name}<br/>"
            f"<b>Card Type</b> {p.card_label}<br/>"
            f"<b>Card Number</b> XXXX XXXX XXXX {p.card_last4}<br/>"
            f"<b>Statement Period</b> {period} (6 months)<br/>"
            f"<b>Payment Due Date</b> {p.due_date.strftime('%d %b %Y')}<br/>"
            f"<b>Credit Limit</b> {_money(float(p.credit_limit))}<br/>"
            f"<b>Available Limit</b> {_money(float(avail))}<br/>"
            f"<b>Total Transactions</b> {len(p.txns)}",
            body,
        ),
        Spacer(1, 8),
        Paragraph("<b>Account Summary</b>", body),
        Paragraph(
            f"Previous Balance {_money(prev_bal)}<br/>"
            f"Payments Received - {_money(payments)}<br/>"
            f"Purchases &amp; Debits {_money(total)}<br/>"
            f"Finance Charges {_money(finance)}<br/>"
            f"<b>Total Amount Due {_money(total_due)}</b><br/>"
            f"<b>Minimum Amount Due {_money(min_due)}</b>",
            body,
        ),
        Spacer(1, 10),
        Paragraph("<b>Transaction Details</b>", body),
        Spacer(1, 4),
        _build_txn_table(p, styles),
        Spacer(1, 10),
        Paragraph(
            f"<b>Reward Summary</b><br/>Reward Points Earned: 12,480<br/>"
            f"Cashback Credited: {_money(2150.0)}<br/>"
            f"<b>EMI Active Plans: {p.emi_plans}</b> (iPhone, MacBook)",
            body,
        ),
        Spacer(1, 6),
        Paragraph(
            "<i>Demo 6-month statement for SmartSpend — flights, hotels, IRCTC, EMIs, ChatGPT, etc. "
            "Not an official HDFC document.</i>",
            small,
        ),
    ]
    doc.build(story)


def write_icici_style(path: Path, p: CcPersona) -> None:
    total = sum(a for _, _, a in p.txns)
    total_due = round(total + 620.0, 2)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.4 * inch,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "T", parent=styles["Heading1"], fontSize=14, textColor=p.brand, fontName=_FONT_BOLD
    )
    body = _para_style(styles, "B", fontSize=9, leading=12)
    small = _para_style(styles, "S", fontSize=7, leading=9)

    period = f"{p.billing_start.strftime('%d %b %Y')} - {p.billing_end.strftime('%d %b %Y')}"
    story = [
        Paragraph("<b>ICICI BANK CREDIT CARD STATEMENT</b>", title),
        Paragraph("<i>SAMPLE / DEMO — 6 MONTHS — NOT OFFICIAL</i>", small),
        Spacer(1, 6),
        Paragraph(
            f"<b>Cardholder</b> : {p.full_name}<br/>"
            f"<b>Card Type</b> : {p.card_label}<br/>"
            f"<b>Card Number</b> : XXXX XXXX XXXX {p.card_last4}<br/>"
            f"<b>Billing Period</b> : {period}<br/>"
            f"<b>Payment Due Date</b> : {p.due_date.strftime('%d %b %Y')}<br/>"
            f"<b>Credit Limit</b> : {_money(float(p.credit_limit))}<br/>"
            f"<b>Transactions</b> : {len(p.txns)}",
            body,
        ),
        Spacer(1, 8),
        Paragraph("<b>Transaction Details</b>", body),
        Spacer(1, 4),
        _build_txn_table(p, styles),
        Spacer(1, 10),
        Paragraph(
            f"<b>Total Amount Due : {_money(total_due)}</b><br/>"
            f"<b>EMI Active Plans : {p.emi_plans}</b>",
            body,
        ),
        Spacer(1, 6),
        Paragraph(
            "<i>Demo 6-month ICICI Coral statement — travel, EMI, ChatGPT, subscriptions. "
            "SmartSpend upload test only.</i>",
            small,
        ),
    ]
    doc.build(story)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p in PERSONAS:
        if p.bank.startswith("HDFC"):
            fname = f"HDFC_CREDIT_CARD_STATEMENT_{p.full_name.replace(' ', '_')}.pdf"
            write_hdfc_style(OUT_DIR / fname, p)
        else:
            fname = f"ICICI_CREDIT_CARD_STATEMENT_{p.full_name.replace(' ', '_')}.pdf"
            write_icici_style(OUT_DIR / fname, p)
        total = sum(a for _, _, a in p.txns)
        sym = "INR-rupee" if _RUPEE_CHAR == "\u20b9" else _RUPEE_CHAR
        print(
            f"Wrote {fname}: {len(p.txns)} txns, total {total:,.2f}, "
            f"currency={sym}, font={_FONT_BODY}, {p.billing_start} to {p.billing_end}"
        )

    print(f"\nPDFs saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
