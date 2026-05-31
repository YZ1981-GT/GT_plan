-- R040: 回滚 ReportConfigBaseline 表 + report_config.is_stale 列

DROP TABLE IF EXISTS report_config_baseline;

ALTER TABLE report_config DROP COLUMN IF EXISTS is_stale;
