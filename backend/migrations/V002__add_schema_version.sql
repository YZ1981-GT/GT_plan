-- V002__add_schema_version.sql
-- 创建 schema_version 表（如果尚不存在）。
-- 注意：MigrationRunner.ensure_schema_version_table() 会在扫描前自动创建此表，
-- 所以此脚本主要用于文档记录和一致性。

CREATE TABLE IF NOT EXISTS schema_version (
    id          SERIAL PRIMARY KEY,
    version     VARCHAR(20)  NOT NULL UNIQUE,
    filename    VARCHAR(255) NOT NULL,
    applied_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    checksum    VARCHAR(64)  NOT NULL
);
