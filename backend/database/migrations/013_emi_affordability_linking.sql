-- EMI Tracker ↔ Purchase Planner linking (affordability + postpone audit)
-- Run after festival_purchase_schema.sql if tables already exist.

ALTER TABLE users ADD COLUMN IF NOT EXISTS monthly_fixed_expenses DECIMAL(12,2) DEFAULT 0;

ALTER TABLE purchase_goals ADD COLUMN IF NOT EXISTS original_target_date DATE;

CREATE TABLE IF NOT EXISTS financial_advice (
  id              SERIAL PRIMARY KEY,
  user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  advice_type     VARCHAR(50) NOT NULL,
  title           TEXT,
  description     TEXT,
  action_items    JSONB,
  severity        VARCHAR(20) DEFAULT 'info',
  created_at      TIMESTAMP DEFAULT NOW(),
  user_action     VARCHAR(20) DEFAULT 'pending',
  executed_at     TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_financial_advice_user_created
  ON financial_advice (user_id, created_at DESC);
