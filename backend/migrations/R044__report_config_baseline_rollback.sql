-- R044: 回滚 ReportConfigBaseline 表 + report_config.is_stale 列
-- 注：原为 R040，因 V040 同号冲突重编号为 V044/R044。

DROP TABLE IF EXISTS report_config_baseline;

ALTER TABLE report_config DROP COLUMN IF EXISTS is_stale;
