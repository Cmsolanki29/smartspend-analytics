-- ============================================================
-- Migration 004: connected_sources + uploaded_documents tables
-- + alter transactions for data_origin tracking
-- Safe to run multiple times (IF NOT EXISTS + ADD COLUMN IF NOT EXISTS)
-- ============================================================

CREATE TABLE IF NOT EXISTS connected_sources (
  id                   SERIAL PRIMARY KEY,
  user_id              INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_type          VARCHAR(50)  NOT NULL CHECK (source_type IN ('bank','credit_card','upi','other')),
  institution_name     VARCHAR(100) NOT NULL,
  account_number_masked VARCHAR(50),
  is_primary           BOOLEAN      DEFAULT false,
  status               VARCHAR(20)  DEFAULT 'active',
  connected_at         TIMESTAMP    DEFAULT NOW(),
  metadata             JSONB
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cs_user_institution
  ON connected_sources(user_id, LOWER(institution_name));
CREATE INDEX IF NOT EXISTS idx_cs_user_type ON connected_sources(user_id, source_type);

CREATE TABLE IF NOT EXISTS uploaded_documents (
  id                          SERIAL PRIMARY KEY,
  user_id                     INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  connected_source_id         INTEGER       REFERENCES connected_sources(id) ON DELETE SET NULL,
  file_name                   VARCHAR(255)  NOT NULL,
  file_type                   VARCHAR(50)   NOT NULL,
  file_size_kb                INTEGER,
  file_path                   TEXT,
  extraction_status           VARCHAR(20)   DEFAULT 'pending'
                                CHECK (extraction_status IN ('pending','processing','completed','failed')),
  extracted_by                VARCHAR(50)   DEFAULT 'openai',
  extraction_confidence       NUMERIC(5,2),
  rows_extracted              INTEGER       DEFAULT 0,
  rows_imported               INTEGER       DEFAULT 0,
  rows_skipped_duplicates     INTEGER       DEFAULT 0,
  uploaded_at                 TIMESTAMP     DEFAULT NOW(),
  processed_at                TIMESTAMP,
  metadata                    JSONB
);
CREATE INDEX IF NOT EXISTS idx_ud_user ON uploaded_documents(user_id, uploaded_at DESC);

-- Extend transactions table
ALTER TABLE transactions
  ADD COLUMN IF NOT EXISTS connected_source_id  INTEGER REFERENCES connected_sources(id),
  ADD COLUMN IF NOT EXISTS uploaded_document_id INTEGER REFERENCES uploaded_documents(id),
  ADD COLUMN IF NOT EXISTS data_origin          VARCHAR(50) DEFAULT 'seed';

CREATE INDEX IF NOT EXISTS idx_txn_connected_source ON transactions(connected_source_id) WHERE connected_source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_txn_uploaded_doc     ON transactions(uploaded_document_id) WHERE uploaded_document_id IS NOT NULL;

-- Backfill existing seed transactions
UPDATE transactions SET data_origin = 'seed' WHERE data_origin IS NULL;
