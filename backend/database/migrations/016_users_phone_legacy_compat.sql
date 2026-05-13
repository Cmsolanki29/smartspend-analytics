-- Legacy servers referenced users.phone for OTP follow-up; the canonical column is mobile_number.
-- Adding phone removes "column phone does not exist" for any stale API process still issuing that UPDATE.

ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);

UPDATE users
SET phone = mobile_number
WHERE phone IS NULL
  AND mobile_number IS NOT NULL;

COMMENT ON COLUMN users.phone IS 'Legacy alias of mobile_number; prefer mobile_number in new code.';
