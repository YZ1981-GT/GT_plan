-- 一次性将所有 TIMESTAMP WITHOUT TIME ZONE 列改为 TIMESTAMP WITH TIME ZONE
-- 所有 naive datetime 视为 UTC（与代码中 datetime.now(timezone.utc) 的语义一致）
-- 生成脚本：可多次重跑（已经是 timestamptz 的列会跳过）

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE data_type = 'timestamp without time zone'
          AND table_schema = 'public'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN %I TYPE TIMESTAMP WITH TIME ZONE USING %I AT TIME ZONE ''UTC''',
            r.table_name, r.column_name, r.column_name
        );
        RAISE NOTICE 'Converted %.% to timestamptz', r.table_name, r.column_name;
    END LOOP;
END $$;

-- 验证：输出剩余的 naive 列（应为 0 行）
SELECT table_name, column_name
FROM information_schema.columns
WHERE data_type = 'timestamp without time zone'
  AND table_schema = 'public'
ORDER BY table_name, column_name;
