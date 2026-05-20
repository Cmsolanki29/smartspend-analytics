# Team onboarding bank statements (upload demo)

**For new signups only** — does not modify `vikram@smartspend.in`, `priya@`, `rahul@`, `ananya@`, or `karan@` database seed data.

## Files (PDF + CSV)

| Person | PDF (recommended for demo) | CSV | Bank | Monthly salary |
|--------|---------------------------|-----|------|----------------|
| Chirag Solanki | `HDFC_CHIRAG_ONBOARDING_STATEMENT_Chirag_Solanki.pdf` | same base name `.csv` | HDFC | INR 92,000 (Vikram-like) |
| Amruta Abhangrao | `ICICI_AMRUTA_ONBOARDING_STATEMENT_Amruta_Abhangrao.pdf` | `.csv` | ICICI | INR 75,000 (Priya-like) |
| Sumit Dabas | `AXIS_SUMIT_ONBOARDING_STATEMENT_Sumit_Dabas.pdf` | `.csv` | Axis | INR 45,000 (Rahul-like) |
| Ganesh Patil | `SBI_GANESH_ONBOARDING_STATEMENT_Ganesh_Patil.pdf` | `.csv` | SBI | INR 1,40,000 (Ananya-like) |
| **Vijay Kumar** | `HDFC_VIJAY_ONBOARDING_STATEMENT_Vijay_Kumar.pdf` | `.csv` | HDFC | INR 85,000 salary, rent 22k, SIP 12k/mo — **~400 txns**, **~31 fraud/dark** rows |

Period: team rows **Feb–May 2026**; **Vijay: Feb 2025 – 14 May 2026**.

**Vijay** = realistic salaried Mumbai profile (salary every month, SIP/FD savings, moderate UPI) plus **FraudShield + Dark Patterns** showcase rows in 2026.

Chirag PDF includes one **CRYPTOX** debit row for FraudShield demo.

## How to demo (Path B onboarding)

1. Sign up with a **new email** (not pre-seeded demo accounts).
2. Source Selection → **Upload Bank Statement**.
3. Upload the **PDF** for that person; institution name = bank from table (e.g. `HDFC Bank`).
4. Wait 30–60s for extraction → Dashboard.

## Regenerate

```bash
# CSV
python backend/scripts/generate_team_onboarding_statements.py

# PDF (requires reportlab: pip install reportlab)
python backend/scripts/generate_team_onboarding_pdfs.py

# Vijay — 700+ transactions (CSV + PDF)
python backend/scripts/generate_vijay_onboarding_statement.py
```
