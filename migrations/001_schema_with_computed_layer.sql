-- ============================================================
-- SMARTSPEND DATABASE v2.0 — SCHEMA WITH COMPUTED LAYER
-- File: migrations/001_schema_with_computed_layer.sql
-- Backend-compatible: INTEGER user IDs, uppercase CREDIT/DEBIT
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────────────────────
-- DROP VIEWS, FUNCTIONS, TRIGGERS FIRST
-- ─────────────────────────────────────────────────────────────
DROP VIEW  IF EXISTS v_financial_health      CASCADE;
DROP VIEW  IF EXISTS v_emi_dashboard         CASCADE;
DROP VIEW  IF EXISTS v_subscription_savings  CASCADE;
DROP FUNCTION IF EXISTS compute_subscription_verdict(INT, INT)  CASCADE;
DROP FUNCTION IF EXISTS compute_subscription_verdict(UUID, UUID) CASCADE;
DROP FUNCTION IF EXISTS compute_financial_health(INT)            CASCADE;
DROP FUNCTION IF EXISTS compute_financial_health(UUID)           CASCADE;
DROP FUNCTION IF EXISTS compute_emi_headroom(INT)                CASCADE;
DROP FUNCTION IF EXISTS compute_emi_headroom(UUID)               CASCADE;
DROP FUNCTION IF EXISTS trg_complete_goal()                      CASCADE;
DROP FUNCTION IF EXISTS trg_close_completed_emi()                CASCADE;

-- ─────────────────────────────────────────────────────────────
-- DROP TABLES (new tables from this schema only;
--   we re-create sessions after users so FK is valid)
-- ─────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS dark_pattern_alerts          CASCADE;
DROP TABLE IF EXISTS ai_insights                  CASCADE;
DROP TABLE IF EXISTS login_sessions               CASCADE;
DROP TABLE IF EXISTS device_trust                 CASCADE;
DROP TABLE IF EXISTS user_festival_plans          CASCADE;
DROP TABLE IF EXISTS festivals                    CASCADE;
DROP TABLE IF EXISTS trips_events                 CASCADE;
DROP TABLE IF EXISTS subscription_cancellations   CASCADE;
DROP TABLE IF EXISTS subscription_usage           CASCADE;
DROP TABLE IF EXISTS emis                         CASCADE;

-- Core tables that backend also uses – drop and rebuild cleanly
DROP TABLE IF EXISTS sessions                     CASCADE;
DROP TABLE IF EXISTS fraud_alerts                 CASCADE;
DROP TABLE IF EXISTS purchase_goals               CASCADE;
DROP TABLE IF EXISTS subscriptions                CASCADE;
DROP TABLE IF EXISTS transactions                 CASCADE;
DROP TABLE IF EXISTS users                        CASCADE;

-- ─────────────────────────────────────────────────────────────
-- USERS  (INTEGER PK — backend uses int(user_id))
-- ─────────────────────────────────────────────────────────────
CREATE TABLE users (
  id                      SERIAL PRIMARY KEY,
  email                   VARCHAR(100)  UNIQUE NOT NULL,
  password_hash           VARCHAR(255),
  name                    VARCHAR(100)  NOT NULL,
  monthly_income          NUMERIC(12,2) NOT NULL DEFAULT 0,
  -- declared_monthly_income is a generated alias so computed functions work
  declared_monthly_income NUMERIC(12,2) GENERATED ALWAYS AS (monthly_income) STORED,
  bank                    VARCHAR(50),
  city                    VARCHAR(100),
  plan                    VARCHAR(20)   DEFAULT 'free',
  savings_goal            NUMERIC(12,2) DEFAULT 0,
  risk_tolerance          VARCHAR(10)   DEFAULT 'MEDIUM'
                            CHECK (risk_tolerance IN ('LOW','MEDIUM','HIGH')),
  is_verified             BOOLEAN       DEFAULT true,
  onboarding_completed    BOOLEAN       DEFAULT true,
  last_login              TIMESTAMP,
  mobile_number           VARCHAR(20),
  monthly_fixed_expenses  NUMERIC(12,2) DEFAULT 0,
  created_at              TIMESTAMP     DEFAULT NOW(),
  updated_at              TIMESTAMP     DEFAULT NOW()
);
CREATE INDEX idx_users_email ON users(email);

-- ─────────────────────────────────────────────────────────────
-- SESSIONS  (backend auth — INTEGER user_id)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE sessions (
  id            SERIAL PRIMARY KEY,
  user_id       INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token         TEXT         NOT NULL UNIQUE,
  refresh_token TEXT         UNIQUE,
  expires_at    TIMESTAMP    NOT NULL,
  ip_address    VARCHAR(45),
  user_agent    TEXT,
  created_at    TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX idx_sessions_token   ON sessions(token);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);

-- ─────────────────────────────────────────────────────────────
-- TRANSACTIONS  (INTEGER ids, uppercase CREDIT/DEBIT)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE transactions (
  id               SERIAL PRIMARY KEY,
  user_id          INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  transaction_date DATE          NOT NULL,
  transaction_time TIME          NOT NULL DEFAULT '12:00:00',
  amount           NUMERIC(12,2) NOT NULL,
  type             VARCHAR(10)   NOT NULL CHECK (type IN ('CREDIT','DEBIT')),
  description      TEXT,
  merchant         VARCHAR(200),
  category         VARCHAR(50),
  payment_method   VARCHAR(30),
  is_recurring     BOOLEAN       DEFAULT false,
  bank_name        VARCHAR(50),
  anomaly_flag     BOOLEAN       DEFAULT false,
  risk_score       INTEGER       DEFAULT 0 CHECK (risk_score BETWEEN 0 AND 100),
  risk_level       VARCHAR(10)   DEFAULT 'LOW'
                     CHECK (risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  ml_processed     BOOLEAN       DEFAULT false,
  is_fraud         BOOLEAN       DEFAULT false,
  anomaly_reason   TEXT,
  balance_after    NUMERIC(12,2),
  reference_number VARCHAR(100),
  hour_of_day      INTEGER,
  day_of_week      INTEGER,
  is_weekend       BOOLEAN,
  is_night_txn     BOOLEAN,
  subcategory      VARCHAR(50),
  location         VARCHAR(200),
  device_id        VARCHAR(255),
  ip_address       VARCHAR(45),
  card_token       VARCHAR(255),
  created_at       TIMESTAMP     DEFAULT NOW()
);
CREATE INDEX idx_transactions_user_date ON transactions(user_id, transaction_date DESC);
CREATE INDEX idx_transactions_category  ON transactions(user_id, category);
CREATE INDEX idx_txn_merchant_user      ON transactions(merchant, user_id) WHERE merchant IS NOT NULL;

-- ─────────────────────────────────────────────────────────────
-- SUBSCRIPTIONS  (backend-compatible column names)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE subscriptions (
  id                       SERIAL PRIMARY KEY,
  user_id                  INTEGER       REFERENCES users(id),
  merchant                 VARCHAR(200),
  amount                   NUMERIC(12,2),
  billing_day              SMALLINT      CHECK (billing_day BETWEEN 1 AND 31),
  next_billing_date        DATE,
  category                 VARCHAR(50),
  status                   VARCHAR(20)   DEFAULT 'active',
  sub_lifecycle            VARCHAR(20)   DEFAULT 'active',
  monthly_cost             NUMERIC(12,2),
  usage_score              INTEGER,
  last_used_days           INTEGER,
  times_charged            INTEGER       DEFAULT 0,
  first_charged            DATE,
  last_charged             DATE,
  current_verdict          VARCHAR(20),
  verdict_confidence       INTEGER,
  verdict_reason           TEXT,
  verdict_monthly_waste    NUMERIC(12,2) DEFAULT 0,
  last_evaluated_at        TIMESTAMP WITH TIME ZONE,
  intelligence_category    VARCHAR(40)   DEFAULT 'other',
  is_pro                   BOOLEAN       DEFAULT false,
  reminder_escalation_tier SMALLINT      NOT NULL DEFAULT 1,
  created_at               TIMESTAMP     DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_sub_user_merchant ON subscriptions(user_id, merchant);
CREATE INDEX idx_sub_user_verdict ON subscriptions(user_id, current_verdict);

-- ─────────────────────────────────────────────────────────────
-- SUBSCRIPTION USAGE  (new — drives verdict computation)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE subscription_usage (
  id              UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         INTEGER   NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subscription_id INTEGER   NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
  used_at         TIMESTAMP NOT NULL,
  duration_minutes INTEGER,
  created_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_subscription_usage_date ON subscription_usage(subscription_id, used_at DESC);

-- ─────────────────────────────────────────────────────────────
-- SUBSCRIPTION CANCELLATIONS  (drives savings computation)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE subscription_cancellations (
  id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  service_name   VARCHAR(255)  NOT NULL,
  monthly_amount NUMERIC(10,2) NOT NULL,
  cancelled_at   DATE          NOT NULL,
  created_at     TIMESTAMP     DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- EMIS  (new rich table — for computed layer + dashboard)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE emis (
  id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  loan_name        VARCHAR(255)  NOT NULL,
  lender           VARCHAR(255)  NOT NULL,
  principal_amount NUMERIC(12,2) NOT NULL,
  emi_amount       NUMERIC(10,2) NOT NULL,
  tenure_months    INTEGER       NOT NULL,
  paid_months      INTEGER       DEFAULT 0,
  start_date       DATE          NOT NULL,
  next_due_date    DATE          NOT NULL,
  interest_rate    NUMERIC(5,2)  DEFAULT 0,
  loan_type        VARCHAR(50),
  status           VARCHAR(20)   DEFAULT 'active' CHECK (status IN ('active','closed','overdue')),
  created_at       TIMESTAMP     DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- PURCHASE GOALS  (backend-compatible column names)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE purchase_goals (
  id                       SERIAL PRIMARY KEY,
  user_id                  INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  item_name                VARCHAR(200)  NOT NULL,
  target_amount            NUMERIC(12,2) NOT NULL,
  saved_amount             NUMERIC(12,2) DEFAULT 0,
  target_date              DATE          NOT NULL,
  monthly_target           NUMERIC(12,2) DEFAULT 0,
  category                 VARCHAR(50)   DEFAULT 'OTHER',
  priority                 VARCHAR(10)   DEFAULT 'MEDIUM',
  status                   VARCHAR(20)   DEFAULT 'SAVING',
  best_buy_month           VARCHAR(200),
  emi_vs_cash              JSONB,
  sacrifice_plan           JSONB,
  original_target_date     DATE,
  linked_festival_key      VARCHAR(50),
  display_timeline_label   VARCHAR(80),
  linked_family_event_id INTEGER,
  created_at               TIMESTAMP     DEFAULT NOW()
);
CREATE INDEX idx_pg_user_status ON purchase_goals(user_id, status);

-- ─────────────────────────────────────────────────────────────
-- FRAUD ALERTS  (backend-compatible column names)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE fraud_alerts (
  id                   SERIAL PRIMARY KEY,
  user_id              INTEGER       REFERENCES users(id),
  transaction_id       INTEGER       REFERENCES transactions(id),
  pattern_matched      VARCHAR(100),
  risk_score           INTEGER,
  amount_at_risk       NUMERIC(12,2),
  warning_message      TEXT,
  hinglish_explanation TEXT,
  user_action          VARCHAR(20)   DEFAULT 'PENDING',
  money_saved          NUMERIC(12,2) DEFAULT 0,
  severity             VARCHAR(10)   DEFAULT 'MEDIUM',
  -- Extra fields for our seed/display
  merchant_name        VARCHAR(255),
  reason               TEXT,
  verdict              VARCHAR(50)   DEFAULT 'pending',
  amount_recovered     NUMERIC(10,2) DEFAULT 0,
  detected_at          TIMESTAMP     DEFAULT NOW(),
  resolved_at          TIMESTAMP,
  created_at           TIMESTAMP     DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- TRIPS & EVENTS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE trips_events (
  id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_name  VARCHAR(255)  NOT NULL,
  event_type  VARCHAR(50)   CHECK (event_type IN ('trip','event','occasion')),
  event_date  DATE          NOT NULL,
  budget      NUMERIC(10,2) NOT NULL,
  saved_amount NUMERIC(10,2) DEFAULT 0,
  destination VARCHAR(255),
  notes       TEXT,
  status      VARCHAR(20)   DEFAULT 'planned',
  created_at  TIMESTAMP     DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- FESTIVALS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE festivals (
  id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  festival_name VARCHAR(255) NOT NULL,
  festival_date DATE         NOT NULL,
  is_global     BOOLEAN      DEFAULT true,
  created_at    TIMESTAMP    DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- USER FESTIVAL PLANS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE user_festival_plans (
  id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  festival_id        UUID          REFERENCES festivals(id) ON DELETE CASCADE,
  custom_event_name  VARCHAR(255),
  event_date         DATE          NOT NULL,
  past_spend_amount  NUMERIC(10,2) DEFAULT 0,
  recommended_budget NUMERIC(10,2),
  is_recurring       BOOLEAN       DEFAULT false,
  created_at         TIMESTAMP     DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- DEVICE TRUST
-- ─────────────────────────────────────────────────────────────
CREATE TABLE device_trust (
  id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  device_name VARCHAR(255) NOT NULL,
  device_type VARCHAR(50),
  city        VARCHAR(100),
  trust_score INTEGER      DEFAULT 100 CHECK (trust_score BETWEEN 0 AND 100),
  last_seen   TIMESTAMP    DEFAULT NOW(),
  created_at  TIMESTAMP    DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- LOGIN SESSIONS  (SmartSpend app logins — separate from auth sessions)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE login_sessions (
  id           UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      INTEGER   NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  device_id    UUID      REFERENCES device_trust(id) ON DELETE CASCADE,
  city         VARCHAR(100),
  logged_in_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_login_sessions_user ON login_sessions(user_id, logged_in_at DESC);

-- ─────────────────────────────────────────────────────────────
-- AI INSIGHTS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE ai_insights (
  id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type       VARCHAR(50)  NOT NULL,
  category   VARCHAR(50),
  title      VARCHAR(255) NOT NULL,
  body       TEXT         NOT NULL,
  created_at TIMESTAMP    DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- DARK PATTERN ALERTS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE dark_pattern_alerts (
  id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subscription_id   INTEGER       REFERENCES subscriptions(id) ON DELETE CASCADE,
  service_name      VARCHAR(255)  NOT NULL,
  amount            NUMERIC(10,2) NOT NULL,
  alert_date        DATE          NOT NULL,
  days_until_charge INTEGER,
  alert_type        VARCHAR(50)   NOT NULL,
  pattern_reason    TEXT          NOT NULL,
  created_at        TIMESTAMP     DEFAULT NOW()
);

-- ═════════════════════════════════════════════════════════════
-- COMPUTED LAYER — FUNCTIONS
-- ═════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────
-- FUNCTION: compute_subscription_verdict
-- Uses subscription_usage table; returns dormant/declining/thriving
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION compute_subscription_verdict(
  p_user_id         INT,
  p_subscription_id INT
)
RETURNS TEXT AS $$
DECLARE
  v_current  INT;
  v_previous INT;
  v_drop_pct NUMERIC;
BEGIN
  SELECT COUNT(*) INTO v_current
  FROM subscription_usage
  WHERE user_id         = p_user_id
    AND subscription_id = p_subscription_id
    AND used_at >= NOW() - INTERVAL '30 days';

  SELECT COUNT(*) INTO v_previous
  FROM subscription_usage
  WHERE user_id         = p_user_id
    AND subscription_id = p_subscription_id
    AND used_at BETWEEN NOW() - INTERVAL '60 days' AND NOW() - INTERVAL '30 days';

  IF v_current < 2 THEN RETURN 'dormant'; END IF;

  IF v_previous > 0 THEN
    v_drop_pct := (v_previous - v_current)::NUMERIC / v_previous * 100;
    IF v_drop_pct > 50 THEN RETURN 'declining'; END IF;
  END IF;

  RETURN 'thriving';
END;
$$ LANGUAGE plpgsql;

-- ─────────────────────────────────────────────────────────────
-- FUNCTION: compute_financial_health
-- Queries transactions + emis + users (all INTEGER user_id)
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION compute_financial_health(p_user_id INT)
RETURNS TABLE (
  total_score         INT,
  savings_rate_score  INT,
  security_score      INT,
  expense_ratio_score INT,
  consistency_score   INT,
  diversity_score     INT
) AS $$
DECLARE
  v_income            NUMERIC;
  v_avg_savings       NUMERIC;
  v_savings_pct       NUMERIC;
  v_total_emi         NUMERIC;
  v_emi_ratio         NUMERIC;
  v_consistent_months INT;
  v_has_investments   BOOLEAN;
BEGIN
  SELECT monthly_income INTO v_income
  FROM users WHERE id = p_user_id;

  SELECT AVG(monthly_saved) INTO v_avg_savings FROM (
    SELECT
      DATE_TRUNC('month', transaction_date) AS month,
      SUM(CASE WHEN type = 'CREDIT' THEN amount ELSE -amount END) AS monthly_saved
    FROM transactions
    WHERE user_id = p_user_id
      AND transaction_date >= NOW() - INTERVAL '6 months'
    GROUP BY 1
  ) t;

  v_savings_pct := COALESCE(v_avg_savings, 0) / NULLIF(v_income, 0) * 100;

  SELECT COALESCE(SUM(emi_amount), 0) INTO v_total_emi
  FROM emis WHERE user_id = p_user_id AND status = 'active';

  v_emi_ratio := v_total_emi / NULLIF(v_income, 0) * 100;

  SELECT COUNT(*) INTO v_consistent_months FROM (
    SELECT DATE_TRUNC('month', transaction_date) AS month
    FROM transactions
    WHERE user_id = p_user_id
      AND transaction_date >= NOW() - INTERVAL '6 months'
    GROUP BY 1
    HAVING SUM(CASE WHEN type = 'CREDIT' THEN amount ELSE -amount END) > 0
  ) t;

  SELECT EXISTS(
    SELECT 1 FROM transactions
    WHERE user_id = p_user_id
      AND LOWER(category) IN ('investment','mutual_fund','stocks','fd','sip')
  ) INTO v_has_investments;

  savings_rate_score  := LEAST(30, FLOOR(v_savings_pct * 30.0 / 30))::INT;
  expense_ratio_score := CASE
    WHEN v_emi_ratio <= 20 THEN 25
    WHEN v_emi_ratio <= 30 THEN 20
    WHEN v_emi_ratio <= 40 THEN 14
    WHEN v_emi_ratio <= 50 THEN  8
    ELSE 3 END;
  consistency_score   := LEAST(15, v_consistent_months * 2)::INT;
  security_score      := CASE
    WHEN v_savings_pct >= 30 THEN 18
    WHEN v_savings_pct >= 20 THEN 14
    WHEN v_savings_pct >= 10 THEN 10
    ELSE 6 END;
  diversity_score     := CASE WHEN v_has_investments THEN 10 ELSE 2 END;
  total_score := savings_rate_score + security_score +
                 expense_ratio_score + consistency_score + diversity_score;
  RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- ─────────────────────────────────────────────────────────────
-- FUNCTION: compute_emi_headroom
-- Uses the new 'emis' table (rich schema)
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION compute_emi_headroom(p_user_id INT)
RETURNS TABLE (
  total_emi_burden      NUMERIC,
  debt_to_income_ratio  NUMERIC,
  safe_new_emi_headroom NUMERIC,
  can_take_new_emi      BOOLEAN,
  status                TEXT
) AS $$
DECLARE
  v_income      NUMERIC;
  v_total_emi   NUMERIC;
  v_safe_limit  NUMERIC;
BEGIN
  SELECT monthly_income INTO v_income FROM users WHERE id = p_user_id;

  SELECT COALESCE(SUM(emi_amount), 0) INTO v_total_emi
  FROM emis WHERE user_id = p_user_id AND status = 'active';

  v_safe_limit          := v_income * 0.30;
  total_emi_burden      := v_total_emi;
  debt_to_income_ratio  := ROUND(v_total_emi / NULLIF(v_income, 0) * 100, 1);
  safe_new_emi_headroom := v_safe_limit - v_total_emi;
  can_take_new_emi      := v_total_emi < v_safe_limit;
  status                := CASE
    WHEN ROUND(v_total_emi / NULLIF(v_income, 0) * 100, 1) > 50 THEN 'critical'
    WHEN ROUND(v_total_emi / NULLIF(v_income, 0) * 100, 1) > 40 THEN 'warning'
    WHEN ROUND(v_total_emi / NULLIF(v_income, 0) * 100, 1) > 30 THEN 'caution'
    ELSE 'healthy' END;
  RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- ═════════════════════════════════════════════════════════════
-- COMPUTED LAYER — VIEWS
-- ═════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW v_financial_health AS
SELECT
  u.id   AS user_id,
  u.email,
  u.name,
  (compute_financial_health(u.id)).total_score,
  (compute_financial_health(u.id)).savings_rate_score,
  (compute_financial_health(u.id)).security_score,
  (compute_financial_health(u.id)).expense_ratio_score,
  (compute_financial_health(u.id)).consistency_score,
  (compute_financial_health(u.id)).diversity_score
FROM users u;

CREATE OR REPLACE VIEW v_emi_dashboard AS
SELECT
  u.id                                              AS user_id,
  u.monthly_income                                  AS declared_monthly_income,
  (compute_emi_headroom(u.id)).total_emi_burden,
  (compute_emi_headroom(u.id)).debt_to_income_ratio,
  (compute_emi_headroom(u.id)).safe_new_emi_headroom,
  (compute_emi_headroom(u.id)).can_take_new_emi,
  (compute_emi_headroom(u.id)).status
FROM users u;

CREATE OR REPLACE VIEW v_subscription_savings AS
SELECT
  user_id,
  SUM(CASE WHEN cancelled_at >= DATE_TRUNC('month', NOW())
           THEN monthly_amount ELSE 0 END) AS saved_this_month,
  SUM(CASE WHEN cancelled_at >= DATE_TRUNC('year', NOW())
           THEN monthly_amount ELSE 0 END) AS saved_this_year,
  SUM(monthly_amount)                       AS saved_all_time,
  COUNT(*)                                  AS total_cancelled
FROM subscription_cancellations
GROUP BY user_id;

-- ═════════════════════════════════════════════════════════════
-- TRIGGERS
-- ═════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION trg_complete_goal() RETURNS TRIGGER AS $$
BEGIN
  IF NEW.saved_amount >= NEW.target_amount THEN NEW.status := 'COMPLETED'; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auto_complete_goal
  BEFORE UPDATE ON purchase_goals
  FOR EACH ROW EXECUTE FUNCTION trg_complete_goal();

CREATE OR REPLACE FUNCTION trg_close_completed_emi() RETURNS TRIGGER AS $$
BEGIN
  IF NEW.paid_months >= NEW.tenure_months THEN NEW.status := 'closed'; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auto_close_emi
  BEFORE UPDATE ON emis
  FOR EACH ROW EXECUTE FUNCTION trg_close_completed_emi();

-- ═════════════════════════════════════════════════════════════
-- SCHEMA COMPLETE — run 002_seed_realistic_10_users.sql next
-- ═════════════════════════════════════════════════════════════
