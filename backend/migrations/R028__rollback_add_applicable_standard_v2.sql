-- R028: 回滚 V028 - 删除 projects.applicable_standard_v2 列

ALTER TABLE projects DROP COLUMN IF EXISTS applicable_standard_v2;
