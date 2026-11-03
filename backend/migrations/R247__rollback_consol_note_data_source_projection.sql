-- R243：回滚合并附注来源投影。
DROP INDEX IF EXISTS ix_cnd_source_mode;
ALTER TABLE consol_note_data
    DROP COLUMN IF EXISTS source_digest,
    DROP COLUMN IF EXISTS source_revision,
    DROP COLUMN IF EXISTS source_operation_id,
    DROP COLUMN IF EXISTS source_mode;
