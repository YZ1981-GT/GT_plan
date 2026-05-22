-- R003__rollback_example_add_comment.sql
-- 回滚 V003__example_add_comment.sql
-- 删除 projects 表的 migration_note 列（如果存在）

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'projects' AND column_name = 'migration_note'
    ) THEN
        ALTER TABLE projects DROP COLUMN migration_note;
    END IF;
END $$;
