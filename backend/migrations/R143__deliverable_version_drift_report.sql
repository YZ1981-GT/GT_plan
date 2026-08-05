-- R143: 回滚 V143（word_export_task_versions.drift_report）
--
-- Spec: deliverable-lineage-wiring-and-writeback-closure — Wave 4 Task 21

ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS drift_report;
