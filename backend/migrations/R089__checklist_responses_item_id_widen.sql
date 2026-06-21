-- R089: Rollback item_id column width (may truncate if custom items > 20 chars exist)

ALTER TABLE checklist_responses
    ALTER COLUMN item_id TYPE VARCHAR(20);
