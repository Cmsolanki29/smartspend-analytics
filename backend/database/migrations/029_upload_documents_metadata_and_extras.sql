-- ============================================================================
-- 029: uploaded_documents columns used by pdf_parser + history parity with 004
-- Fixes UndefinedColumn on failure path (metadata) and any minimal legacy tables.
-- Apply: cd backend && python -m scripts.apply_migrations
-- ============================================================================

ALTER TABLE uploaded_documents
  ADD COLUMN IF NOT EXISTS file_path TEXT,
  ADD COLUMN IF NOT EXISTS extracted_by VARCHAR(50) DEFAULT 'openai',
  ADD COLUMN IF NOT EXISTS extraction_confidence NUMERIC(5, 2),
  ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS metadata JSONB,
  ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMP DEFAULT NOW();

ALTER TABLE connected_sources
  ADD COLUMN IF NOT EXISTS metadata JSONB,
  ADD COLUMN IF NOT EXISTS connected_at TIMESTAMP DEFAULT NOW();
