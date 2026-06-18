-- R088: Rollback conclusion column width (data may truncate if values > 5 chars)

ALTER TABLE checklist_responses
    ALTER COLUMN conclusion TYPE VARCHAR(5);
