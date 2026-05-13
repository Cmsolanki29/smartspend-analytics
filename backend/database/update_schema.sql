-- Add mobile number to users table
ALTER TABLE users
ADD COLUMN IF NOT EXISTS mobile_number VARCHAR(15);

-- Create OTP verification table
CREATE TABLE IF NOT EXISTS otp_verifications (
  id SERIAL PRIMARY KEY,
  mobile_number VARCHAR(15) NOT NULL,
  otp_code VARCHAR(6) NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  verified BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_otp_mobile ON otp_verifications(mobile_number);
