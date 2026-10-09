-- R179：回滚 V179
-- 删除 report_config 的调整列公式字段。已配置的公式数据将丢失。

ALTER TABLE report_config
    DROP COLUMN IF EXISTS aje_formula;

ALTER TABLE report_config
    DROP COLUMN IF EXISTS rje_formula;
