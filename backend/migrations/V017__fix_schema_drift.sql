-- V017__fix_schema_drift.sql
-- 修复 alembic chain 历史漂移导致的 PG 列/类型缺失。
--
-- 背景：本仓库启动迁移使用 D6 设计 = 版本化 SQL（MigrationRunner，不是 alembic）。
-- 多个 alembic spec 历史变更没有完整跑齐，导致 PG schema 与 ORM Mapped[] 不一致。
-- 本脚本为根治补丁，遵循 idempotent 原则，可重复执行。
--
-- 修复范围：
--   1. job_status_enum：ORM 用 job_status_enum，PG 只有 job_status，建 alias enum
--   2. import_jobs.version：F 系列乐观锁列（P1-Q1）
--   3. import_jobs.force_submit：F42 / Sprint 7.10 规模警告强制继续
--   4. import_jobs.creator_chain：F22 / Sprint 5.9 接管链路记录

BEGIN;

-- 1. job_status_enum 别名（ORM 用 _enum 后缀）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_status_enum') THEN
        IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_status') THEN
            -- 已有 job_status，重命名为 job_status_enum 以匹配 ORM
            ALTER TYPE job_status RENAME TO job_status_enum;
        ELSE
            -- 都没有，新建 job_status_enum
            CREATE TYPE job_status_enum AS ENUM (
                'pending','queued','running','validating','writing',
                'activating','completed','failed','canceled','timed_out','interrupted'
            );
        END IF;
    END IF;
END $$;

-- 1b. 补 interrupted 值（ORM 已加但旧 enum 没有）
ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'interrupted';

-- 2. import_jobs.version
ALTER TABLE import_jobs
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0;

-- 3. import_jobs.force_submit
ALTER TABLE import_jobs
    ADD COLUMN IF NOT EXISTS force_submit BOOLEAN NOT NULL DEFAULT false;

-- 4. import_jobs.creator_chain
ALTER TABLE import_jobs
    ADD COLUMN IF NOT EXISTS creator_chain JSONB DEFAULT '[]'::jsonb;

COMMIT;
