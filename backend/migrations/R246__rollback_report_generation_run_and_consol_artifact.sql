-- R242：回滚共享报表运行与合并 artifact。
-- 注意：仅回滚 schema；已生成的物理 artifact 文件由运维按清单单独清理，避免误删。

DROP TABLE IF EXISTS consol_artifact;

DROP INDEX IF EXISTS ix_financial_report_run_id;
ALTER TABLE financial_report DROP COLUMN IF EXISTS provenance;
ALTER TABLE financial_report DROP COLUMN IF EXISTS run_id;

DROP TABLE IF EXISTS report_generation_run;
