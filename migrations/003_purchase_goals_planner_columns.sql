-- Purchase Planner API expects these columns on purchase_goals.
-- Safe to run on existing DBs (idempotent).

ALTER TABLE purchase_goals ADD COLUMN IF NOT EXISTS best_buy_month VARCHAR(200);
ALTER TABLE purchase_goals ADD COLUMN IF NOT EXISTS emi_vs_cash JSONB;
ALTER TABLE purchase_goals ADD COLUMN IF NOT EXISTS sacrifice_plan JSONB;
ALTER TABLE purchase_goals ADD COLUMN IF NOT EXISTS original_target_date DATE;
ALTER TABLE purchase_goals ADD COLUMN IF NOT EXISTS linked_festival_key VARCHAR(50);
ALTER TABLE purchase_goals ADD COLUMN IF NOT EXISTS display_timeline_label VARCHAR(80);
ALTER TABLE purchase_goals ADD COLUMN IF NOT EXISTS linked_family_event_id INTEGER;
