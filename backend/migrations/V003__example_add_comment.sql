-- V003__example_add_comment.sql
-- Example migration: add migration_note column to projects table.
-- The DO block uses standard PG dollar-quoting to ensure idempotency.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'projects' AND column_name = 'migration_note'
    ) THEN
        ALTER TABLE projects ADD COLUMN migration_note TEXT;
    END IF;
END $$;
