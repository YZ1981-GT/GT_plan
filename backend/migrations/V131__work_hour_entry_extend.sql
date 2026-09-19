-- V131: 工时自动采集+二次编辑扩展（additive，幂等）
ALTER TABLE work_hour_entries ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual';
ALTER TABLE work_hour_entries ADD COLUMN IF NOT EXISTS source_ref VARCHAR(200);
ALTER TABLE work_hour_entries ADD COLUMN IF NOT EXISTS edit_history JSONB DEFAULT '[]';
ALTER TABLE work_hour_entries ADD COLUMN IF NOT EXISTS activity_type VARCHAR(30);
ALTER TABLE work_hour_entries ADD COLUMN IF NOT EXISTS time_slots JSONB;

CREATE INDEX IF NOT EXISTS idx_whe_source_date ON work_hour_entries(user_id, date, source) WHERE source = 'auto_collected';
CREATE INDEX IF NOT EXISTS idx_whe_timer_dedup ON work_hour_entries(user_id, date, project_id, wp_code) WHERE source = 'timer';
