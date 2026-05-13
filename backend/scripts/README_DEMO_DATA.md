# Demo synthetic transactions (PostgreSQL)

Deterministic loader for hackathon/judge demos: `generate_demo_transactions.py`. Uses the same `.env` database variables as `backend/services/seed_database.py` (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`), **psycopg2**, and **`random.seed(42)`** for reproducible rows.

## Judge one-liner

**~25k txns / ~3 years / 5 Indian urban personas; every user ≥100 rows (configurable floor ≥80); realistic UPI + EMI ladders + Diwali discretionary bump + pre-flagged anomalies for ML.**

## Personas (seeded users)

| Order | Email | Name | Monthly income (₹) | Notes |
|------|-------|------|-------------------|--------|
| 1 | `aanya_rich@demo.smartspend.local` | Aanya Mehta | 3,50,000 | High volume weight; multiple EMIs |
| 2 | `rahul_upper@demo.smartspend.local` | Rahul Sharma | 1,20,000 | Upper-middle weight |
| 3 | `priya_middle@demo.smartspend.local` | Priya Nair | 65,000 | Middle weight |
| 4 | `vikram_stretched@demo.smartspend.local` | Vikram Patil | 45,000 | Stretched; lower discretionary end-of-month |
| 5 | `neha_student@demo.smartspend.local` | Neha Kulkarni | 15,000 | One small EMI chain + Netflix-style subs + micro-UPI |

Users are **inserted or updated** by email (`ON CONFLICT (email) DO UPDATE`). Final **transaction count per user** = `--min-per-user` (after clamp ≥80) **plus** a share of `(total − users × min)` allocated by persona income weights, **±2** when the optional same-day “UPI probe + large debit” pair is added (only if `total − users × min ≥ 2` and a persona with income ≥ ₹1,00,000 is included). The script logs each user’s count after load and exits non-zero if any demo user is below the floor.

## CLI

```text
python backend/scripts/generate_demo_transactions.py --total 25000 --min-per-user 100 --clear-demo
python backend/scripts/generate_demo_transactions.py --total 20000 --min-per-user 80 --dry-run
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--total` | 25000 | Clamped to **20000–30000**. |
| `--min-per-user` | 100 | Hard floor **80**; values below 80 are clamped with a warning. |
| `--users` | 5 | Up to **5** personas (fixed list). |
| `--clear-demo` | off | Deletes **only** transactions for users whose email is `LIKE '%@demo.smartspend.local'`. Also removes `fraud_alerts` rows pointing at those transactions if the table exists. Does **not** delete non-demo users or CSV-seeded data. |
| `--dry-run` | off | Connects to read `information_schema` / `bank_name`; prints planned parameters and a sample skeleton size; **no inserts**. |

**Pre-check:** if `total < users × min` after clamping, the script aborts with a clear message.

**Minimum `--min-per-user` vs calendar months:** there must be enough rows for one **salary** and one **rent** per month in the rolling ~3-year window (≈ `2 × month_count`). If `--min-per-user` is below that, the script exits with an error.

## Rollback

Re-run with `--clear-demo` (optionally before a fresh load):

```bash
python backend/scripts/generate_demo_transactions.py --clear-demo
```

Then load again without `--clear-demo` if you want new synthetic data.

## Behaviour summary

- **Date range:** transaction dates uniform in `[today − 3 years, today]` for discretionary rows; salary/rent/EMI anchored on calendar months in that window.
- **`bank_name`:** if `transactions.bank_name` exists (see `seed_database.ensure_bank_name_column`), inserts set `SYNTH_DEMO`; otherwise the column is omitted.
- **ML-related columns:** `hour_of_day`, `day_of_week`, `is_weekend`, `is_night_txn` derived like `seed_database._txn_features`; `anomaly_flag`, `risk_score`, `risk_level`, `anomaly_reason`, `ml_processed` populated (non-anomaly rows stay `LOW` / low scores).
- **Performance:** bulk insert via `psycopg2.extras.execute_values` with page size **1000**; then `ANALYZE transactions`.
- **Optional TODO:** rebuild or refresh **`monthly_summary`** (and any other aggregates) if your deployment depends on it for dashboards—this script does not do that automatically.

## Acceptance checklist (manual)

- [ ] `SELECT COUNT(*) FROM transactions JOIN users u ON u.id = user_id WHERE u.email LIKE '%@demo.smartspend.local'` in **[20000, 30000]** (or your clamped `--total`).
- [ ] `MIN(count) GROUP BY user_id` for demo users ≥ `max(80, --min-per-user)`.
- [ ] Salary credits, rent debits, and EMI merchant strings visible per user in raw SQL.
- [ ] Anomaly debits roughly **3–6%** of demo debits (`anomaly_flag = TRUE`).
- [ ] EMI-related APIs show non-zero burden for users 1–4 (rich → stretched) after load.

## API / schema

This task does **not** change application code. If your database is missing optional columns (e.g. `bank_name`), add them using your normal migration path or `ensure_bank_name_column` from CSV seeding before relying on `bank_name` in inserts.
