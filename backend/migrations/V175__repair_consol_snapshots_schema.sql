-- V175：修复 V174 合并快照表在先行 metadata.create_all() 环境中的 schema 漂移
--
-- V174 负责首次建表；若启动时 ORM 的 create_all() 已先创建同名表，
-- CREATE TABLE IF NOT EXISTS 不会补齐 server default 或时区类型，
-- 因而这里用幂等 ALTER 统一到 V174/ORM 契约。

ALTER TABLE consol_snapshots
    ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE consol_snapshots
    ALTER COLUMN created_at SET DEFAULT now();

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'consol_snapshots'
          AND column_name = 'created_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE consol_snapshots
            ALTER COLUMN created_at TYPE TIMESTAMPTZ
            USING created_at AT TIME ZONE 'UTC';
    END IF;
END
$$;
