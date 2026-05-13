# Indian fintech transaction seed corpus

Production-style **template pool** (25k+ rows) plus **30 urban personas** for SmartSpend demos: EMI cadence, subscriptions, festival spend, food/transport variance, and seeded fraud motifs (₹1 trap pairs, duplicate charges).

## Schema (`database_schema.sql`)

Tables:

| Table | Role |
|-------|------|
| `user_personas` | Income tier, city tier, age band, loan flags — used to filter templates |
| `transaction_seed_data` | Template rows (amount, merchant, frequency, income band, flags) |
| `user_transaction_assignments` | Audit trail when a user receives a corpus assignment |

Apply once (PostgreSQL):

```bash
psql -U postgres -d smartspend_db -f backend/database/migrations/017_indian_fintech_seed_corpus.sql
```

Equivalent file: `backend/database/seed_corpus/database_schema.sql`.

## Generate corpus (Python)

From `backend/`:

```bash
# CSV only (default 26_000 rows, deterministic seed 42)
python -m scripts.generate_indian_fintech_corpus --total 26000 --csv database/seed_corpus/transaction_seed_data.csv

# Load into PostgreSQL (truncates pool first)
python -m scripts.generate_indian_fintech_corpus --total 26000 --db --clear-seed
```

- **`--total`**: scales category mix proportionally (minimum 1 row per bucket).
- **`--clear-seed`**: `TRUNCATE transaction_seed_data` before insert (does **not** delete app `transactions`).
- Personas are **upserted** whenever you run `--db`.

## Assign to a user

Requires the pool in DB (`--db` step). Then:

```bash
python -m scripts.assign_user_transactions you@example.com
python -m scripts.assign_user_transactions you@example.com --count 1400 --persona rahul_sw_blr
```

- **`--count`**: target materialized rows (monthly templates expand to several `transactions` each).
- **`--persona`**: `persona_key` from `user_personas` (see `services/indian_fintech_seed/personas.py`). Omit for random persona.

## Signup integration (optional)

Set in `.env`:

```env
SMARTSPEND_SEED_CORPUS=1
```

When enabled, **new signups** pull from `transaction_seed_data` instead of the generic numeric seed. You must still **load the corpus into Postgres** first (`generate_indian_fintech_corpus.py --db`). `seed_demo_workspace` still runs afterward for goals/festivals/alerts.

## Category mix (default 26_000)

| Bucket | Approx rows |
|--------|----------------|
| income | 1_300 |
| emi | 2_600 |
| subscription | 1_500 |
| food | 4_800 |
| transport | 2_900 |
| shopping | 3_800 |
| utility | 2_000 |
| entertainment | 1_900 |
| health | 1_400 |
| festival | 2_000 |
| fraud | 500 |
| misc | 1_300 |

## Implementation map (deliverable names)

| Spec name | In repo |
|-----------|---------|
| `database_schema.sql` | `backend/database/seed_corpus/database_schema.sql` + migration `017_*.sql` |
| `generate_transactions.py` | `backend/scripts/generate_indian_fintech_corpus.py` + `services/indian_fintech_seed/corpus_generator.py` |
| `assign_user_transactions.py` | `backend/scripts/assign_user_transactions.py` + `services/indian_fintech_seed/assign.py` |
| `transaction_seed_data.csv` | Generate with `--csv database/seed_corpus/transaction_seed_data.csv` (gitignored if large) |

## Validation

After `--db`:

```sql
SELECT category, COUNT(*) FROM transaction_seed_data GROUP BY 1 ORDER BY 2 DESC;
SELECT COUNT(*) FROM user_personas;
```

After assignment:

```sql
SELECT COUNT(*) FROM transactions WHERE user_id = <id>;
```
