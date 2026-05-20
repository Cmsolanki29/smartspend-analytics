#!/usr/bin/env python3
"""
Generate PDF bank statements for team onboarding uploads (Chirag, Amruta, Sumit, Ganesh).

Reuses transaction data from generate_team_onboarding_statements.py.
Does NOT modify pre-seeded demo users in the database.

Run from repo root:
  python backend/scripts/generate_team_onboarding_pdfs.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Import persona builders from sibling script
_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from generate_team_onboarding_statements import (  # noqa: E402
    PERSONAS,
    Persona,
    Txn,
    build_persona_txns,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "test samples" / "onboarding"

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError as exc:
    raise SystemExit("Install reportlab: pip install reportlab") from exc


def _fmt_date(d: date, bank: str) -> str:
    if bank == "hdfc":
        return d.strftime("%d/%m/%Y")
    if bank == "sbi":
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return f"{d.day:02d} {months[d.month - 1]} {d.year}"
    return d.strftime("%d-%m-%Y")


def _narration_hdfc(t: Txn, p: Persona, ref: str) -> str:
    if t.kind == "credit":
        return f"NEFT-HDFC0001234-{p.employer}-SALARY-{ref}"
    if "Rent" in t.desc:
        return f"NEFT DR-SBIN0012345-LANDLORD RENT-{ref}"
    if "EMI" in t.desc:
        return f"ACH DR {t.desc.upper()}"
    if "CRYPTOX" in t.desc:
        return t.desc
    return f"UPI-{t.desc[:50]}-pay@ybl"


def _narration_icici(t: Txn, p: Persona, ref: str) -> str:
    if t.kind == "credit":
        return f"NEFT CR {p.employer} SALARY"
    if "Rent" in t.desc:
        return f"NEFT DR LANDLORD RENT {ref}"
    if "EMI" in t.desc:
        return f"ACH DR {t.desc}"
    return f"UPI/DR/{ref}/{t.desc[:40]}/Payment"


def _narration_axis(t: Txn, p: Persona, ref: str) -> str:
    if t.kind == "credit":
        return f"NEFT INWARD {p.employer} SALARY"
    if "Rent" in t.desc:
        return f"NEFT OUTWARD RENT {ref}"
    if "EMI" in t.desc:
        return f"ACH DR {t.desc}"
    return f"UPI {t.desc[:45]}"


def _narration_sbi(t: Txn, p: Persona, ref: str) -> str:
    if t.kind == "credit":
        return f"NEFT CR-{p.employer}-SALARY-{ref}"
    if "Rent" in t.desc:
        return f"NEFT DR-RENT-{ref}"
    if "EMI" in t.desc:
        return f"ACH DR {t.desc}"
    return f"UPI/{ref}/{t.desc[:35]}/Payment"


def _rows_for_pdf(p: Persona, txns: list[Txn]) -> tuple[list[str], list[list[str]]]:
    refn = int(f"{p.rng_seed}"[:7])
    bal = {
        "hdfc": 85_000.0,
        "icici": 72_000.0,
        "axis": 38_000.0,
        "sbi": 120_000.0,
    }[p.bank_fmt]

    if p.bank_fmt == "hdfc":
        header = ["Date", "Narration", "Chq/Ref", "Withdrawal (INR)", "Deposit (INR)", "Balance (INR)"]
        rows: list[list[str]] = []
        for t in txns:
            ref = f"N{refn}"
            refn += 1
            nar = _narration_hdfc(t, p, ref)
            if t.kind == "credit":
                bal += t.amount
                rows.append([_fmt_date(t.d, p.bank_fmt), nar, ref, "", f"{t.amount:,.2f}", f"{bal:,.2f}"])
            else:
                bal -= t.amount
                rows.append([_fmt_date(t.d, p.bank_fmt), nar, ref, f"{t.amount:,.2f}", "", f"{bal:,.2f}"])
        return header, rows

    if p.bank_fmt == "icici":
        header = ["Txn Date", "Description", "Ref", "Withdrawal (INR)", "Deposit (INR)", "Balance (INR)"]
        rows = []
        for t in txns:
            ref = str(refn)
            refn += 1
            nar = _narration_icici(t, p, ref)
            ds = _fmt_date(t.d, p.bank_fmt)
            if t.kind == "credit":
                bal += t.amount
                rows.append([ds, nar, ref[-8:], "", f"{t.amount:,.2f}", f"{bal:,.2f}"])
            else:
                bal -= t.amount
                rows.append([ds, nar, ref[-8:], f"{t.amount:,.2f}", "", f"{bal:,.2f}"])
        return header, rows

    if p.bank_fmt == "axis":
        header = ["Tran Date", "Particulars", "Chq/Ref", "Withdrawal", "Deposit", "Closing Balance"]
        rows = []
        for t in txns:
            ref = str(refn)
            refn += 1
            part = _narration_axis(t, p, ref)
            ds = _fmt_date(t.d, p.bank_fmt)
            if t.kind == "credit":
                bal += t.amount
                rows.append([ds, part, ref, "", f"{t.amount:,.2f}", f"{bal:,.2f}"])
            else:
                bal -= t.amount
                rows.append([ds, part, ref, f"{t.amount:,.2f}", "", f"{bal:,.2f}"])
        return header, rows

    # SBI
    header = ["Txn Date", "Description", "Ref No.", "Debit (INR)", "Credit (INR)", "Balance (INR)"]
    rows = []
    for t in txns:
        ref = str(refn)
        refn += 1
        desc = _narration_sbi(t, p, ref)
        ds = _fmt_date(t.d, p.bank_fmt)
        if t.kind == "credit":
            bal += t.amount
            rows.append([ds, desc, ref, "", f"{t.amount:,.2f}", f"{bal:,.2f}"])
        else:
            bal -= t.amount
            rows.append([ds, desc, ref, f"{t.amount:,.2f}", "", f"{bal:,.2f}"])
    return header, rows


def _bank_theme(p: Persona) -> tuple[str, colors.Color]:
    themes = {
        "hdfc": ("HDFC Bank", colors.HexColor("#004C8F")),
        "icici": ("ICICI Bank", colors.HexColor("#F58220")),
        "axis": ("Axis Bank", colors.HexColor("#97144D")),
        "sbi": ("State Bank of India", colors.HexColor("#22409A")),
    }
    return themes[p.bank_fmt]


def write_pdf(path: Path, p: Persona, txns: list[Txn]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bank_name, brand = _bank_theme(p)
    header_cols, data_rows = _rows_for_pdf(p, txns)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.45 * inch,
        title=f"{bank_name} Statement - {p.full_name}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BankTitle",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=brand,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#333333"),
        alignment=TA_LEFT,
        leading=12,
    )
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=7, leading=9)

    story = [
        Paragraph(f"<b>{bank_name}</b> — Savings Account Statement", title_style),
        Spacer(1, 6),
        Paragraph(
            f"<b>Account Holder:</b> {p.full_name}<br/>"
            f"<b>Account Number:</b> XXXX{p.account_suffix} &nbsp;&nbsp; "
            f"<b>Branch:</b> {p.city}<br/>"
            f"<b>Statement Period:</b> 01 Feb 2026 to 14 May 2026<br/>"
            f"<b>Monthly Salary (credits):</b> INR {p.salary:,.0f} &nbsp;&nbsp; "
            f"<b>Currency:</b> INR",
            sub_style,
        ),
        Spacer(1, 10),
        Paragraph("<b>Transaction Details</b>", sub_style),
        Spacer(1, 6),
    ]

    # Chunk rows for readability (reportlab handles page breaks on large tables)
    table_data = [header_cols]
    for row in data_rows:
        wrapped = [
            row[0],
            Paragraph(row[1].replace("&", "&amp;")[:120], small),
            row[2],
            row[3],
            row[4],
            row[5],
        ]
        table_data.append(wrapped)

    col_widths = [0.85 * inch, 3.8 * inch, 0.75 * inch, 1.0 * inch, 1.0 * inch, 1.05 * inch]
    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), brand),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (2, 1), (2, -1), "CENTER"),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(tbl)
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "<i>This is a demo statement generated for SmartSpend onboarding. "
            "Not an official bank document.</i>",
            ParagraphStyle("Foot", parent=styles["Normal"], fontSize=7, textColor=colors.grey),
        )
    )

    doc.build(story)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p in PERSONAS:
        txns = build_persona_txns(p)
        fname = f"{p.bank_fmt.upper()}_{p.key.upper()}_ONBOARDING_STATEMENT_{p.full_name.replace(' ', '_')}.pdf"
        out = OUT_DIR / fname
        write_pdf(out, p, txns)
        print(f"Wrote {out} ({len(txns)} transactions)")

    print(f"\nPDFs saved to: {OUT_DIR}")
    print("Upload these in Source Selection -> Upload Bank Statement (same as CSV).")


if __name__ == "__main__":
    main()
