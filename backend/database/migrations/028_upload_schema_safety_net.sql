-- ============================================================================
-- 028: Upload / multi-source column safety net (idempotent)
-- Fixes UndefinedColumn when 004/005/027 were never applied to this DB.
-- Canonical apply:  cd backend && python -m scripts.apply_migrations
-- ============================================================================

-- connected_sources (documents.py INSERT + GET /sources/connected)
ALTER TABLE connected_sources
  ADD COLUMN IF NOT EXISTS is_visible_on_dashboard BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS added_via VARCHAR(50) DEFAULT 'settings_upload',
  ADD COLUMN IF NOT EXISTS account_number_masked VARCHAR(50),
  ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS is_primary BOOLEAN DEFAULT FALSE;

UPDATE connected_sources SET is_visible_on_dashboard = TRUE WHERE is_visible_on_dashboard IS NULL;
UPDATE connected_sources SET status = 'active' WHERE status IS NULL;

-- uploaded_documents (INSERT + history + pdf_parser status updates)
ALTER TABLE uploaded_documents
  ADD COLUMN IF NOT EXISTS connected_source_id INTEGER REFERENCES connected_sources(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS extraction_status VARCHAR(20) DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS rows_extracted INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rows_imported INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rows_skipped_duplicates INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rows_skipped_invalid INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS error_message TEXT,
  ADD COLUMN IF NOT EXISTS file_size_kb INTEGER;

-- transactions (pdf_parser INSERT)
ALTER TABLE transactions
  ADD COLUMN IF NOT EXISTS connected_source_id INTEGER REFERENCES connected_sources(id),
  ADD COLUMN IF NOT EXISTS uploaded_document_id INTEGER REFERENCES uploaded_documents(id),
  ADD COLUMN IF NOT EXISTS data_origin VARCHAR(50) DEFAULT 'seed';

UPDATE transactions SET data_origin = 'seed' WHERE data_origin IS NULL;

CREATE INDEX IF NOT EXISTS idx_connected_sources_visible
  ON connected_sources(user_id, is_visible_on_dashboard);

CREATE INDEX IF NOT EXISTS idx_txn_connected_source ON transactions(connected_source_id)
  WHERE connected_source_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_txn_uploaded_doc ON transactions(uploaded_document_id)
  WHERE uploaded_document_id IS NOT NULL;
