-- Indian fintech demo corpus: template pool + personas + assignment audit trail.
-- Apply: psql -U postgres -d smartspend_db -f backend/database/seed_corpus/database_schema.sql

CREATE TABLE IF NOT EXISTS user_personas (
  id                SERIAL PRIMARY KEY,
  persona_key       VARCHAR(64) UNIQUE NOT NULL,
  name              VARCHAR(100) NOT NULL,
  age               INTEGER,
  occupation        VARCHAR(120),
  city              VARCHAR(80),
  city_tier         INTEGER CHECK (city_tier IN (1, 2, 3)),
  monthly_income    DECIMAL(12, 2) NOT NULL,
  lifestyle         VARCHAR(40),
  age_group         VARCHAR(20),
  has_home_loan     BOOLEAN DEFAULT FALSE,
  home_loan_emi      DECIMAL(12, 2),
  has_vehicle_loan  BOOLEAN DEFAULT FALSE,
  vehicle_loan_emi  DECIMAL(12, 2),
  has_personal_loan BOOLEAN DEFAULT FALSE,
  personal_loan_emi DECIMAL(12, 2),
  food_delivery_freq VARCHAR(32),
  shopping_style    VARCHAR(32),
  subscription_count INTEGER DEFAULT 0,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_personas_income ON user_personas (monthly_income);
CREATE INDEX IF NOT EXISTS idx_user_personas_tier ON user_personas (city_tier);

CREATE TABLE IF NOT EXISTS transaction_seed_data (
  id                  SERIAL PRIMARY KEY,
  category            VARCHAR(50) NOT NULL,
  subcategory         VARCHAR(80),
  merchant_name       VARCHAR(255) NOT NULL,
  amount              DECIMAL(12, 2) NOT NULL,
  transaction_type    VARCHAR(10) NOT NULL CHECK (transaction_type IN ('DEBIT', 'CREDIT')),
  description         TEXT,
  frequency           VARCHAR(24),
  day_of_month        INTEGER CHECK (day_of_month IS NULL OR (day_of_month >= 1 AND day_of_month <= 31)),
  typical_hour        INTEGER CHECK (typical_hour IS NULL OR (typical_hour >= 0 AND typical_hour <= 23)),
  min_income          DECIMAL(12, 2),
  max_income          DECIMAL(12, 2),
  age_group           VARCHAR(20),
  city_tier           INTEGER CHECK (city_tier IS NULL OR city_tier IN (1, 2, 3)),
  lifestyle           VARCHAR(40),
  is_emi              BOOLEAN DEFAULT FALSE,
  is_subscription     BOOLEAN DEFAULT FALSE,
  is_fraud_pattern      BOOLEAN DEFAULT FALSE,
  fraud_type            VARCHAR(50),
  seasonal_tag        VARCHAR(40),
  created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seed_income ON transaction_seed_data (min_income, max_income);
CREATE INDEX IF NOT EXISTS idx_seed_tier ON transaction_seed_data (city_tier);
CREATE INDEX IF NOT EXISTS idx_seed_age ON transaction_seed_data (age_group);
CREATE INDEX IF NOT EXISTS idx_seed_category ON transaction_seed_data (category);
CREATE INDEX IF NOT EXISTS idx_seed_fraud ON transaction_seed_data (is_fraud_pattern) WHERE is_fraud_pattern = TRUE;

CREATE TABLE IF NOT EXISTS user_transaction_assignments (
  id              SERIAL PRIMARY KEY,
  user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  persona_id      INTEGER REFERENCES user_personas(id) ON DELETE SET NULL,
  template_count  INTEGER NOT NULL,
  date_span_days  INTEGER,
  assigned_at     TIMESTAMPTZ DEFAULT NOW(),
  notes           VARCHAR(500)
);

CREATE INDEX IF NOT EXISTS idx_assign_user ON user_transaction_assignments (user_id, assigned_at DESC);
