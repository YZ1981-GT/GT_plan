-- 工作表生成的草稿绑定服务端来源版本与摘要。
ALTER TABLE elimination_entries
    ADD COLUMN IF NOT EXISTS source_version JSONB;
ALTER TABLE elimination_entries
    ADD COLUMN IF NOT EXISTS source_digest VARCHAR(64);

CREATE INDEX IF NOT EXISTS ix_elimination_entries_source_digest
    ON elimination_entries (project_id, year, source_digest)
    WHERE source_digest IS NOT NULL AND is_deleted = false;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_elimination_entries_source_digest'
    ) THEN
        ALTER TABLE elimination_entries
            ADD CONSTRAINT ck_elimination_entries_source_digest
            CHECK (source_digest IS NULL OR length(source_digest) = 64);
    END IF;
END
$$;
