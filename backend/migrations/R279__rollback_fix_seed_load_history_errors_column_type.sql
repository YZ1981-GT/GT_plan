-- R276: 回滚 V276（errors 列型还原为 integer）
--
-- 回滚保护：还原前对含 JSONB 非空数组（真实错误明细）的行 RAISE EXCEPTION。
-- 空数组 / legacy count 数组可无损还原（按数组首元素反解条数）。

DO $$
DECLARE
    current_type TEXT;
    nonempty_rows INTEGER;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'seed_load_history'
           AND column_name = 'errors'
    ) THEN
        RETURN;  -- 列不存在，无需回滚
    END IF;

    SELECT data_type INTO current_type
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'seed_load_history'
       AND column_name = 'errors';

    IF current_type IS DISTINCT FROM 'jsonb' THEN
        RETURN;  -- 已是 integer，幂等
    END IF;

    SELECT COUNT(*) INTO nonempty_rows
      FROM seed_load_history
     WHERE jsonb_array_length(errors) > 0
       AND NOT (
           jsonb_array_length(errors) = 1
           AND (errors->>0) LIKE 'legacy error count: %'
       );

    IF nonempty_rows > 0 THEN
        RAISE EXCEPTION 'R276 回滚保护：seed_load_history 有 % 行含真实 JSONB 错误明细，还原 integer 会丢数据（先人工归档）',
            nonempty_rows;
    END IF;

    ALTER TABLE seed_load_history
        ADD COLUMN IF NOT EXISTS errors_int INTEGER NOT NULL DEFAULT 0;

    UPDATE seed_load_history
       SET errors_int = CASE
               WHEN jsonb_array_length(errors) = 1
                    AND errors->>0 LIKE 'legacy error count: %'
               THEN (regexp_replace(errors->>0, '^legacy error count: ', ''))::integer
               ELSE 0
           END;

    ALTER TABLE seed_load_history DROP COLUMN errors;
    ALTER TABLE seed_load_history RENAME COLUMN errors_int TO errors;

    RAISE NOTICE 'R276: seed_load_history.errors jsonb -> integer 完成';
END $$;
