-- Optional festival linkage for Purchase Planner goals (EMI affordability shift-to-festival UX).
ALTER TABLE purchase_goals ADD COLUMN IF NOT EXISTS linked_festival_key VARCHAR(50);
ALTER TABLE purchase_goals ADD COLUMN IF NOT EXISTS display_timeline_label VARCHAR(80);
