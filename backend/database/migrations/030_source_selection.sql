-- Migration 030: source selection onboarding
-- dashboard_mode already exists on users; this is a safety net + adds
-- the onboarding_complete_source column so we can track HOW the user
-- completed setup (bank | credit_card | bank_statement | skipped).

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS dashboard_mode VARCHAR(50) DEFAULT 'bank_only',
  ADD COLUMN IF NOT EXISTS onboarding_source VARCHAR(50) DEFAULT NULL;
