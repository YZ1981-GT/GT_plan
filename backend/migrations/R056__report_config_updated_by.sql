-- R056: 回滚 report_config.updated_by
ALTER TABLE report_config DROP COLUMN IF EXISTS updated_by;
