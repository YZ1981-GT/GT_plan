DROP INDEX IF EXISTS ix_elimination_entries_source_digest;
ALTER TABLE elimination_entries DROP CONSTRAINT IF EXISTS ck_elimination_entries_source_digest;
ALTER TABLE elimination_entries DROP COLUMN IF EXISTS source_digest;
ALTER TABLE elimination_entries DROP COLUMN IF EXISTS source_version;
