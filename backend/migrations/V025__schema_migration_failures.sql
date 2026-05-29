-- V025: 迁移失败追踪表（migration-runner-resilience spec）
--
-- 设计要点：
-- 1. 每个失败的 V*.sql 在此表记录一行，PK = version
-- 2. ON CONFLICT (version) UPDATE 累计 attempt_count，便于诊断反复失败的迁移
-- 3. 成功执行后 _clear_failure 删除该行（schema_version 写入即代表成功）
-- 4. 与 schema_version 的关系：schema_version 仅记录成功，本表仅记录失败，互斥

CREATE TABLE IF NOT EXISTS schema_migration_failures (
    version         VARCHAR(20)  PRIMARY KEY,
    filename        VARCHAR(255) NOT NULL,
    error_type      VARCHAR(100) NOT NULL,
    error_message   TEXT         NOT NULL,
    attempted_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    attempt_count   INTEGER      NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_schema_migration_failures_attempted_at
    ON schema_migration_failures (attempted_at DESC);
