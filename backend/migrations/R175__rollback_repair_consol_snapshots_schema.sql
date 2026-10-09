-- R175：回滚 V175（仅撤销 V175 对既有列定义的修复）
-- 注意：不会删除 consol_snapshots 数据或表。

ALTER TABLE consol_snapshots
    ALTER COLUMN id DROP DEFAULT;

ALTER TABLE consol_snapshots
    ALTER COLUMN created_at DROP DEFAULT;

ALTER TABLE consol_snapshots
    ALTER COLUMN created_at TYPE TIMESTAMP
    USING created_at AT TIME ZONE 'UTC';
