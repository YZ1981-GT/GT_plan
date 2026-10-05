-- R178：回滚 V178
-- 注意：删除 version/source binding/source audit 列会丢失 Runtime CAS 与审计元数据，
-- 执行前必须确认没有依赖这些字段的运行记录。

ALTER TABLE wp_formula
    DROP COLUMN IF EXISTS binding;

ALTER TABLE wp_formula
    DROP COLUMN IF EXISTS source_scope;

ALTER TABLE draft_refresh_snapshot
    DROP COLUMN IF EXISTS source_scope;

ALTER TABLE draft_refresh_snapshot
    DROP COLUMN IF EXISTS source_formula_id;

ALTER TABLE consol_worksheet_data
    DROP COLUMN IF EXISTS version;
