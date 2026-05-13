-- Migration 019: Performance indexes for new tables + critical existing tables

-- monthly_snapshots: fast lookup by user + month/year
CREATE INDEX IF NOT EXISTS idx_ms_user_month_year ON monthly_snapshots(user_id, year DESC, month DESC);

-- impact_log: fast lookups by user, ordered by time
CREATE INDEX IF NOT EXISTS idx_il_user_created ON impact_log(user_id, created_at DESC);

-- notifications: unread notifications per user (most common query)
CREATE INDEX IF NOT EXISTS idx_notif_user_read_date ON notifications(user_id, is_read, created_at DESC);

-- family_events: user + status + date
CREATE INDEX IF NOT EXISTS idx_fe_user_status ON family_events(user_id, status);
CREATE INDEX IF NOT EXISTS idx_fe_effective_date ON family_events(user_id, planned_date);

-- purchase_goals: active goals per user (critical query in financial engine)
CREATE INDEX IF NOT EXISTS idx_pg_user_status ON purchase_goals(user_id, status);

-- emi_records: active EMIs per user (summed in financial engine)
CREATE INDEX IF NOT EXISTS idx_emr_user_active ON emi_records(user_id, is_active);

-- festival_budgets: upcoming festivals (90-day window)
CREATE INDEX IF NOT EXISTS idx_fb_user_date ON festival_budgets(user_id, festival_date);

-- transactions: major query driver
CREATE INDEX IF NOT EXISTS idx_txn_user_date ON transactions(user_id, transaction_date DESC);
