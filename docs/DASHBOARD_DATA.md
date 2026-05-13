# Dashboard data sources

- **Spending by category** (`GET /analysis/{user_id}/spending?month=&year=`) aggregates **transactions** for that calendar month only (DEBIT rows by category).
- **12-month trends** (`GET /analysis/{user_id}/trends`) prefers **`monthly_summary`** (last 12 rows). If that table is empty or every row has zero income and zero expense, the API **falls back** to aggregating **transactions** (CREDIT vs DEBIT per month) for the rolling 12 calendar months ending at `CURRENT_DATE`. Trends are **user-wide**, not filtered by the dashboard month picker.
- Rebuild `monthly_summary` in production (batch/ETL) if you rely on stored health scores there; the fallback still merges `health_score` / `anomaly_count` from `monthly_summary` when a row exists for that month.
