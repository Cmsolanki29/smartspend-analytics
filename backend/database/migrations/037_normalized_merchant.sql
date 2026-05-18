-- Phase 1: merchant key for trust rules + consistent categorization
ALTER TABLE transactions
  ADD COLUMN IF NOT EXISTS normalized_merchant VARCHAR(100);

UPDATE transactions
SET normalized_merchant = LEFT(
  LOWER(REGEXP_REPLACE(COALESCE(merchant, description, ''), '[^a-z]', '', 'g')),
  100
)
WHERE normalized_merchant IS NULL OR TRIM(normalized_merchant) = '';

CREATE INDEX IF NOT EXISTS idx_txn_user_normalized_merchant
  ON transactions(user_id, normalized_merchant)
  WHERE normalized_merchant IS NOT NULL AND normalized_merchant <> '';

-- Ghost / placeholder sources (per-user, not shared demo data)
ALTER TABLE connected_sources
  ADD COLUMN IF NOT EXISTS is_ghost BOOLEAN DEFAULT FALSE;
