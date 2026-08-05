-- R142: 回滚 V142（word_export_task_versions 的 edited_by / edited_at）
--
-- Spec: deliverable-lineage-wiring-and-writeback-closure — Wave 2 Task 14

ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS edited_at;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS edited_by;
