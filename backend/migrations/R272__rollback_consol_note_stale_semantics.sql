ALTER TABLE consol_note_data
    DROP COLUMN IF EXISTS stale_at;
ALTER TABLE consol_note_data
    DROP COLUMN IF EXISTS stale_reason;
