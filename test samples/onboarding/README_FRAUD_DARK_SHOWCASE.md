# FraudShield + Dark Patterns QA CSV (50-day window)

## File

`HDFC_FRAUD_DARK_SHOWCASE_QA.csv`

All showcase rows are packed into **50 consecutive days** so you can verify the app without hunting across many months.

| Metric | Value |
|--------|--------|
| Period | **01 Mar 2026 – 19 Apr 2026** (50 days) |
| Total rows | ~**70** (12 normal + ~58 showcase) |
| Calendar months | **March 2026** (~45 rows) + **April 2026** (~25 rows) |

## Regenerate

```bash
python backend/scripts/generate_fraud_dark_showcase_csv.py
```

## Upload

1. **New email** signup.
2. Upload `HDFC_FRAUD_DARK_SHOWCASE_QA.csv` → institution **HDFC Bank**.
3. View mode **Merged**.
4. Wait **60–90 s** → hard refresh.

## Transactions month picker (important)

The UI shows **one month at a time**:

| Select month | What you see |
|--------------|----------------|
| **March 2026** | Most rows (~45) — duplicates, trials, crypto, velocity prep |
| **April 2026** | Rest (~25) — second salary, CRYPTOX, velocity **day 47** (17 Apr) |

**Dark Patterns** and **FraudShield** scan the **full 50-day ledger** (not month-filtered) — open those tabs after upload for the full picture.

## Expected results

### Dark Patterns (full scan)

- **Patterns detected:** aim for **12+** (often 15–22)
- DUPLICATE (6 pairs), FREE_TRIAL (6+ chains), EK_RUPEE (10+ ₹1 rows), PRICE_INCREASE (2 merchants), ESCALATING (KYC ladder)

### FraudShield (after background batch)

- Many HIGH/CRITICAL alerts across unknown payees, crypto, scam text, micro ₹1–10, large debits
- **Velocity:** 17 Apr 2026 — 3× ~₹8.3k (pick **April** on Transactions)

### Transactions → Anomalies Only

- **March 2026:** 15+ flagged rows typical
- **April 2026:** 8+ flagged rows typical

## Quick demo script (2 min)

1. Upload CSV → wait 90 s.
2. **Dark Patterns** → count patterns + scroll timeline.
3. **FraudShield** → alert list.
4. **Transactions** → month **March 2026** → Anomalies Only.
5. Switch to **April 2026** → see velocity triple (17 Apr).

## If still empty

- Fresh user only; backend on 8002; wait 90 s; Merged view; Reload Dark Patterns.
