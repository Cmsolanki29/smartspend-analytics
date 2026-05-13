-- Migration 018: Interconnected Financial System
-- impact_log, notifications, family_events, monthly_snapshots

-- ── 1. Impact Log (audit trail of cascading changes) ─────────────────────────
CREATE TABLE IF NOT EXISTS impact_log (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trigger_type  VARCHAR(60) NOT NULL,   -- emi_added | event_postponed | purchase_updated | festival_updated | emi_closed | income_updated
    trigger_id    INTEGER,                -- FK to the thing that changed (nullable for income changes)
    affected_entities JSONB DEFAULT '[]', -- [{type, id, name, field_changed, old_val, new_val}]
    summary_text  TEXT,
    surplus_before NUMERIC(12,2),
    surplus_after  NUMERIC(12,2),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_impact_log_user_id ON impact_log(user_id);
CREATE INDEX IF NOT EXISTS idx_impact_log_created_at ON impact_log(created_at DESC);

-- ── 2. Notifications ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type          VARCHAR(40) NOT NULL DEFAULT 'info',  -- info | warning | alert | success
    title         VARCHAR(200) NOT NULL,
    body          TEXT NOT NULL,
    is_read       BOOLEAN NOT NULL DEFAULT FALSE,
    action_type   VARCHAR(60),   -- navigate_to | postpone_goal | review_emi | null
    action_payload JSONB DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, is_read);

-- ── 3. Family Events / Trips ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS family_events (
    id                      SERIAL PRIMARY KEY,
    user_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_name              VARCHAR(200) NOT NULL,
    event_type              VARCHAR(60) NOT NULL DEFAULT 'trip',  -- trip | celebration | medical | other
    planned_date            DATE NOT NULL,
    actual_date             DATE,
    estimated_cost          NUMERIC(12,2) NOT NULL DEFAULT 0,
    status                  VARCHAR(30) NOT NULL DEFAULT 'planned',  -- planned | postponed | completed | cancelled
    postpone_reason         TEXT,
    postponed_to_date       DATE,
    linked_purchase_goal_id INTEGER REFERENCES purchase_goals(id) ON DELETE SET NULL,
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_family_events_user_id ON family_events(user_id);
CREATE INDEX IF NOT EXISTS idx_family_events_planned_date ON family_events(planned_date);

-- ── 4. Monthly Snapshots (computed each recalculation) ───────────────────────
CREATE TABLE IF NOT EXISTS monthly_snapshots (
    id                      SERIAL PRIMARY KEY,
    user_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    month                   SMALLINT NOT NULL,
    year                    SMALLINT NOT NULL,
    total_income            NUMERIC(12,2) NOT NULL DEFAULT 0,
    fixed_expenses          NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_emi_outgo         NUMERIC(12,2) NOT NULL DEFAULT 0,
    festival_monthly_reserve NUMERIC(12,2) NOT NULL DEFAULT 0,
    event_monthly_reserve   NUMERIC(12,2) NOT NULL DEFAULT 0,
    purchase_monthly_reserve NUMERIC(12,2) NOT NULL DEFAULT 0,
    available_surplus       NUMERIC(12,2) NOT NULL DEFAULT 0,
    surplus_status          VARCHAR(20) NOT NULL DEFAULT 'healthy',  -- healthy | warning | critical
    breakdown_json          JSONB DEFAULT '{}',
    computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, month, year)
);
CREATE INDEX IF NOT EXISTS idx_monthly_snapshots_user ON monthly_snapshots(user_id);

-- ── 5. Add linked_family_event_id to purchase_goals (if not exists) ──────────
ALTER TABLE purchase_goals
    ADD COLUMN IF NOT EXISTS linked_family_event_id INTEGER REFERENCES family_events(id) ON DELETE SET NULL;

-- ── 6. Add purchase_goal_id link to festival_budgets ─────────────────────────
ALTER TABLE festival_budgets
    ADD COLUMN IF NOT EXISTS linked_purchase_goal_id INTEGER REFERENCES purchase_goals(id) ON DELETE SET NULL;

-- Seed a sample family event for Rahul (user_id 38) — Family weekend trip
INSERT INTO family_events (user_id, event_name, event_type, planned_date, estimated_cost, status)
SELECT 38, 'Family Weekend Trip', 'trip', '2027-01-07', 42000, 'planned'
WHERE NOT EXISTS (SELECT 1 FROM family_events WHERE user_id = 38 AND event_name ILIKE '%family%trip%')
  AND EXISTS (SELECT 1 FROM users WHERE id = 38);
