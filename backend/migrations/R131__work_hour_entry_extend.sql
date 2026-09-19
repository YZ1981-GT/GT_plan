-- R131: 回滚 V131
DROP INDEX IF EXISTS idx_whe_timer_dedup;
DROP INDEX IF EXISTS idx_whe_source_date;
ALTER TABLE work_hour_entries DROP COLUMN IF EXISTS time_slots;
ALTER TABLE work_hour_entries DROP COLUMN IF EXISTS activity_type;
ALTER TABLE work_hour_entries DROP COLUMN IF EXISTS edit_history;
ALTER TABLE work_hour_entries DROP COLUMN IF EXISTS source_ref;
ALTER TABLE work_hour_entries DROP COLUMN IF EXISTS source;
