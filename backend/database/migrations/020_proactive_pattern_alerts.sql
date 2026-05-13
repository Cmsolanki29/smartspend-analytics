-- Proactive dark-pattern / subscription charge alerts (T-3 style reminders)
-- Idempotent: IF NOT EXISTS / ON CONFLICT safe

CREATE TABLE IF NOT EXISTS pattern_alerts (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  pattern_type VARCHAR(50) NOT NULL,
  merchant_name VARCHAR(255) NOT NULL,
  charge_amount NUMERIC(12,2) NOT NULL,
  charge_date DATE NOT NULL,
  action_deadline TIMESTAMPTZ NOT NULL,
  first_alert_date DATE NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'snoozed', 'acted', 'dismissed', 'expired')),
  times_snoozed INTEGER NOT NULL DEFAULT 0,
  last_snoozed_at TIMESTAMPTZ,
  snooze_until TIMESTAMPTZ,
  acted_at TIMESTAMPTZ,
  action_taken VARCHAR(50),
  notification_channels JSONB NOT NULL DEFAULT '{"in_app": false, "email": false, "sms": false}'::jsonb,
  last_notification_sent_at TIMESTAMPTZ,
  source_transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
  predicted_confidence NUMERIC(4,2),
  details_json JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, pattern_type, merchant_name, charge_date)
);

CREATE INDEX IF NOT EXISTS idx_pattern_alerts_user_status_date
  ON pattern_alerts (user_id, status, charge_date);

CREATE INDEX IF NOT EXISTS idx_pattern_alerts_upcoming
  ON pattern_alerts (charge_date, status)
  WHERE status IN ('pending', 'snoozed');

CREATE TABLE IF NOT EXISTS merchant_cancellation_info (
  id SERIAL PRIMARY KEY,
  merchant_name VARCHAR(255) NOT NULL UNIQUE,
  cancellation_method VARCHAR(20)
    CHECK (cancellation_method IS NULL OR cancellation_method IN ('web', 'phone', 'email', 'app', 'impossible')),
  cancellation_url TEXT,
  cancellation_phone VARCHAR(40),
  cancellation_email VARCHAR(120),
  difficulty_rating INTEGER CHECK (difficulty_rating IS NULL OR difficulty_rating BETWEEN 1 AND 5),
  cancellation_steps TEXT[],
  estimated_time_minutes INTEGER,
  total_user_reports INTEGER NOT NULL DEFAULT 0,
  successful_cancellations INTEGER NOT NULL DEFAULT 0,
  failed_cancellations INTEGER NOT NULL DEFAULT 0,
  avg_refund_time_days INTEGER,
  user_tips TEXT[],
  known_issues TEXT[],
  last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_savings_tracker (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  month DATE NOT NULL,
  patterns_detected INTEGER NOT NULL DEFAULT 0,
  patterns_prevented INTEGER NOT NULL DEFAULT 0,
  patterns_ignored INTEGER NOT NULL DEFAULT 0,
  potential_losses NUMERIC(12,2) NOT NULL DEFAULT 0,
  actual_savings NUMERIC(12,2) NOT NULL DEFAULT 0,
  disputes_filed INTEGER NOT NULL DEFAULT 0,
  refunds_received NUMERIC(12,2) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, month)
);

CREATE TABLE IF NOT EXISTS alert_action_log (
  id SERIAL PRIMARY KEY,
  alert_id INTEGER NOT NULL REFERENCES pattern_alerts(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  action_type VARCHAR(50) NOT NULL,
  action_details JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_action_log_alert ON alert_action_log (alert_id);

CREATE TABLE IF NOT EXISTS notification_queue (
  id SERIAL PRIMARY KEY,
  alert_id INTEGER NOT NULL REFERENCES pattern_alerts(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  channel VARCHAR(20) NOT NULL CHECK (channel IN ('in_app', 'email', 'sms', 'push')),
  scheduled_for TIMESTAMPTZ NOT NULL,
  sent_at TIMESTAMPTZ,
  status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
  retry_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notification_queue_pending
  ON notification_queue (scheduled_for, status)
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_user_savings_tracker_user_month
  ON user_savings_tracker (user_id, month);

-- Seed a small cancellation corpus (expand anytime)
INSERT INTO merchant_cancellation_info (
  merchant_name, cancellation_method, cancellation_url, difficulty_rating,
  cancellation_steps, estimated_time_minutes, user_tips, known_issues
) VALUES
(
  'Netflix',
  'web',
  'https://www.netflix.com/cancelplan',
  2,
  ARRAY['Sign in', 'Account → Cancel membership', 'Confirm'],
  3,
  ARRAY['You keep access until period end'],
  ARRAY[]::text[]
),
(
  'Amazon Prime',
  'web',
  'https://www.amazon.in/gp/primecentral',
  2,
  ARRAY['Your Account → Prime', 'Manage / End membership', 'Confirm'],
  4,
  ARRAY['Refund rules depend on usage'],
  ARRAY[]::text[]
),
(
  'Spotify Premium',
  'web',
  'https://www.spotify.com/account/subscription/',
  2,
  ARRAY['Account → Subscription', 'Cancel Premium', 'Confirm'],
  2,
  ARRAY['Playlists remain after downgrade'],
  ARRAY[]::text[]
),
(
  'Hotstar',
  'web',
  'https://www.hotstar.com/in/subscribe/my-account',
  3,
  ARRAY['My Account → Subscriptions', 'Cancel auto-renew', 'Confirm'],
  6,
  ARRAY['Turn off auto-renew before renewal date'],
  ARRAY[]::text[]
),
(
  'YouTube Premium',
  'web',
  'https://www.youtube.com/paid_memberships',
  2,
  ARRAY['Paid memberships', 'Manage → Cancel'],
  3,
  ARRAY['Family plan: only primary can cancel'],
  ARRAY[]::text[]
)
ON CONFLICT (merchant_name) DO NOTHING;
