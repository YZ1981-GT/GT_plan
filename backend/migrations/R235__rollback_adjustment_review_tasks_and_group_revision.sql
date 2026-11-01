-- R235：回滚 V235 调整分录组复核基础设施

DROP POLICY IF EXISTS project_isolation ON adjustment_treatment_events;
DROP POLICY IF EXISTS project_isolation ON adjustment_review_tasks;

DROP TRIGGER IF EXISTS trg_adjustments_group_number_unique ON adjustments;
DROP FUNCTION IF EXISTS gt_check_adjustment_group_number();

DROP POLICY IF EXISTS project_isolation ON adjustment_client_bookings;
DROP TABLE IF EXISTS adjustment_client_bookings;

DROP INDEX IF EXISTS ix_adjustment_treatment_events_group_time;
DROP TABLE IF EXISTS adjustment_treatment_events;

DROP INDEX IF EXISTS ix_adjustment_review_tasks_assignees_gin;
DROP INDEX IF EXISTS ix_adjustment_review_tasks_project_status;
DROP INDEX IF EXISTS uq_adjustment_review_tasks_active_group;
DROP TABLE IF EXISTS adjustment_review_tasks;

DROP INDEX IF EXISTS uq_adjustment_entries_active_group_line;
ALTER TABLE adjustment_entries DROP CONSTRAINT IF EXISTS ck_adjustment_entries_one_side;
ALTER TABLE adjustment_entries DROP CONSTRAINT IF EXISTS ck_adjustment_entries_nonnegative;
ALTER TABLE adjustments DROP CONSTRAINT IF EXISTS ck_adjustments_audit_phase;
ALTER TABLE adjustments DROP CONSTRAINT IF EXISTS ck_adjustments_content_revision;
ALTER TABLE adjustments DROP COLUMN IF EXISTS audit_phase;
ALTER TABLE adjustments DROP COLUMN IF EXISTS content_revision;
ALTER TABLE unadjusted_misstatements DROP COLUMN IF EXISTS management_communication_at;
