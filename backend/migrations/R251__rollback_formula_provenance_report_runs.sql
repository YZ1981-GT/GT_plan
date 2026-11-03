-- R236: 回滚 V251。执行前必须先回退 S5 报表 provenance 代码。

DROP INDEX IF EXISTS idx_financial_report_project_year_run;
ALTER TABLE financial_report DROP CONSTRAINT IF EXISTS fk_financial_report_run;
ALTER TABLE financial_report DROP COLUMN IF EXISTS provenance;
ALTER TABLE financial_report DROP COLUMN IF EXISTS run_id;
DROP INDEX IF EXISTS idx_report_generation_run_project_year_started;
DROP TABLE IF EXISTS report_generation_run;
