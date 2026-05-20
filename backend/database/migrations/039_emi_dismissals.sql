-- User-dismissed EMI patterns (survives re-scan / live detection)
CREATE TABLE IF NOT EXISTS emi_dismissals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dismiss_key VARCHAR(512) NOT NULL,
    merchant_label VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, dismiss_key)
);

CREATE INDEX IF NOT EXISTS idx_emi_dismissals_user ON emi_dismissals(user_id);

-- Hide preset/custom festival cards user removed from planner
CREATE TABLE IF NOT EXISTS festival_dismissals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    festival_name VARCHAR(120) NOT NULL,
    festival_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, festival_name, festival_date)
);

CREATE INDEX IF NOT EXISTS idx_festival_dismissals_user ON festival_dismissals(user_id);
