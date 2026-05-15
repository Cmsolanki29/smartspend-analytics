-- ============================================================================
-- 027: Multi-source safety net (idempotent, non-destructive)
-- Adds columns/indexes required by uploads + pdf import if an older DB missed 004/005.
-- For CHECK constraints, unique keys, and seed backfill, run repo migrations
--   migrations/004_connected_sources_and_documents.sql
--   migrations/005_multi_source_accounts.sql
-- ============================================================================

ALTER TABLE connected_sources
  ADD COLUMN IF NOT EXISTS account_number_masked VARCHAR(50),
  ADD COLUMN IF NOT EXISTS is_visible_on_dashboard BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS added_via VARCHAR(50) DEFAULT 'settings_upload';

UPDATE connected_sources SET is_visible_on_dashboard = TRUE WHERE is_visible_on_dashboard IS NULL;

ALTER TABLE uploaded_documents
  ADD COLUMN IF NOT EXISTS connected_source_id INTEGER REFERENCES connected_sources(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS extraction_status VARCHAR(20) DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS rows_extracted INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rows_imported INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rows_skipped_duplicates INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rows_skipped_invalid INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS error_message TEXT;

ALTER TABLE transactions
  ADD COLUMN IF NOT EXISTS connected_source_id INTEGER REFERENCES connected_sources(id),
  ADD COLUMN IF NOT EXISTS uploaded_document_id INTEGER REFERENCES uploaded_documents(id),
  ADD COLUMN IF NOT EXISTS data_origin VARCHAR(50) DEFAULT 'seed';

CREATE INDEX IF NOT EXISTS idx_connected_sources_visible
  ON connected_sources(user_id, is_visible_on_dashboard);

CREATE INDEX IF NOT EXISTS idx_txn_connected_source ON transactions(connected_source_id)
  WHERE connected_source_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_txn_uploaded_doc ON transactions(uploaded_document_id)
  WHERE uploaded_document_id IS NOT NULL;
