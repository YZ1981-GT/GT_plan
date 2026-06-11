-- R069: 回滚报表行次映射 mapping_sign 列
-- 对应 V069__report_line_mapping_sign.sql

ALTER TABLE report_line_mapping DROP COLUMN IF EXISTS mapping_sign;
