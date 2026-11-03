-- R229: 回滚 V229（financial_report.calc_version / calc_error）
-- 回滚后新代码读写这两列即报错（列不存在）：先回退代码，再执行本回滚。
ALTER TABLE financial_report DROP COLUMN IF EXISTS calc_error;
ALTER TABLE financial_report DROP COLUMN IF EXISTS calc_version;
