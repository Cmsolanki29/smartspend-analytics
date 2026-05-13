-- OTP: store expiry/created as TIMESTAMPTZ so comparisons with NOW() are unambiguous
-- and Python drivers never need to compare naive vs aware datetimes for this table.

ALTER TABLE otp_verifications
  ALTER COLUMN expires_at TYPE TIMESTAMPTZ
  USING (expires_at AT TIME ZONE 'UTC');

ALTER TABLE otp_verifications
  ALTER COLUMN created_at TYPE TIMESTAMPTZ
  USING (CASE
    WHEN created_at IS NULL THEN NOW()
    ELSE (created_at AT TIME ZONE 'UTC')
  END);

ALTER TABLE otp_verifications
  ALTER COLUMN created_at SET DEFAULT NOW();
