-- R129 回滚：移除 disclosure_notes.stale_source（V129）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'disclosure_notes' AND column_name = 'stale_source'
    ) THEN
        ALTER TABLE disclosure_notes DROP COLUMN stale_source;
    END IF;
END $$;
