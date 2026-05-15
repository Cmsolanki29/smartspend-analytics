-- ============================================================================
-- Migration 005: Multi-source accounts (dashboard mode, source visibility,
-- seed bank linkage). Idempotent where possible.
-- ============================================================================

-- Users: dashboard view preference (seed/demo bank txns = NULL connected_source_id)
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS dashboard_mode VARCHAR(50) DEFAULT 'merged';

UPDATE users SET dashboard_mode = 'merged' WHERE dashboard_mode IS NULL;

COMMENT ON COLUMN users.dashboard_mode IS 'bank_only | credit_card_only | merged';

-- connected_sources: visibility + provenance
ALTER TABLE connected_sources
  ADD COLUMN IF NOT EXISTS is_visible_on_dashboard BOOLEAN DEFAULT TRUE NOT NULL,
  ADD COLUMN IF NOT EXISTS added_via VARCHAR(50) DEFAULT 'settings_upload';

UPDATE connected_sources SET is_visible_on_dashboard = TRUE WHERE is_visible_on_dashboard IS NULL;

-- Relax / extend source_type (drop old CHECK if present)
ALTER TABLE connected_sources DROP CONSTRAINT IF EXISTS connected_sources_source_type_check;
ALTER TABLE connected_sources
  ADD CONSTRAINT connected_sources_source_type_check
  CHECK (source_type IN ('bank','credit_card','upi','other','bank_statement_pdf'));

-- Unique per user + institution + type (allows same brand as bank vs card)
DROP INDEX IF EXISTS idx_cs_user_institution;
ALTER TABLE connected_sources DROP CONSTRAINT IF EXISTS connected_sources_user_inst_type_key;
ALTER TABLE connected_sources
  ADD CONSTRAINT connected_sources_user_inst_type_key
  UNIQUE (user_id, institution_name, source_type);

-- uploaded_documents: optional diagnostics
ALTER TABLE uploaded_documents
  ADD COLUMN IF NOT EXISTS rows_skipped_invalid INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS error_message TEXT;

CREATE INDEX IF NOT EXISTS idx_connected_sources_visible
  ON connected_sources(user_id, is_visible_on_dashboard);

-- Seed primary bank row for existing users (demo data) and link orphan seed txns
INSERT INTO connected_sources (
  user_id, source_type, institution_name, account_number_masked,
  is_primary, is_visible_on_dashboard, added_via, status
)
SELECT
  u.id,
  'bank',
  COALESCE(NULLIF(TRIM(u.bank), ''), 'Demo Bank'),
  'XXXX' || LPAD((MOD(u.id * 7919, 10000))::text, 4, '0'),
  TRUE,
  TRUE,
  'signup',
  'active'
FROM users u
WHERE NOT EXISTS (
  SELECT 1 FROM connected_sources cs
  WHERE cs.user_id = u.id AND cs.source_type = 'bank' AND cs.is_primary = TRUE
)
ON CONFLICT ON CONSTRAINT connected_sources_user_inst_type_key DO NOTHING;

UPDATE transactions t
SET connected_source_id = cs.id
FROM connected_sources cs
WHERE t.user_id = cs.user_id
  AND cs.source_type = 'bank'
  AND cs.is_primary = TRUE
  AND t.connected_source_id IS NULL
  AND COALESCE(t.data_origin, 'seed') = 'seed';
