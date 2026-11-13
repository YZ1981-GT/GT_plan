-- R251: 回滚 V251。执行前必须先回退 S5 报表 provenance 代码。
-- V251 排在 V246 之后：report_generation_run 表与 financial_report.run_id / provenance 由 V246 建立（其 CREATE TABLE /
-- ADD COLUMN IF NOT EXISTS 在这里都是空操作），归 R246 回滚。本脚本只撤销 V251 实际新增的三个对象，
-- 不删 V246 的表与列（spec formula-management-repair-closure R0.1）。
DROP INDEX IF EXISTS idx_financial_report_project_year_run;
ALTER TABLE financial_report DROP CONSTRAINT IF EXISTS fk_financial_report_run;
DROP INDEX IF EXISTS idx_report_generation_run_project_year_started;
