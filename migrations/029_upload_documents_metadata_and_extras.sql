-- Mirror of backend/database/migrations/029_upload_documents_metadata_and_extras.sql

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
