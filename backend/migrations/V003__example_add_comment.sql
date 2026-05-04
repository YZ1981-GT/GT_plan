-- V003__example_add_comment.sql
-- 示例迁移：为 projects 表添加 migration_note 列（演示迁移流程）。
-- 如果列已存在则跳过（DO $$ ... END $$; 块保证幂等）。

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'projects' AND column_name = 'migration_note'
    ) THEN
        ALTER TABLE projects ADD COLUMN migration_note TEXT;
    END IF;
END $$;
