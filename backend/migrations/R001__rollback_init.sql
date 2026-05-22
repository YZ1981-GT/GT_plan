-- R001__rollback_init.sql
-- 回滚 V001__init.sql（初始化基线）
--
-- ⚠️ WARNING: V001 是 no-op 基线脚本（现有 schema 由 SQLAlchemy create_all 创建）。
-- 回滚 V001 意味着 DROP 所有业务表，这将导致 **全部数据丢失**，仅适用于：
--   1. 开发环境完全重建
--   2. 灾难恢复后从备份还原
--
-- 此脚本 **不执行任何 DDL 操作**，仅作为文档记录。
-- 如确需清空数据库，请使用 pg_dump 备份后手动执行 DROP SCHEMA public CASCADE。
--
-- 若需自动化清空（仅限开发环境），取消下方注释：
-- DROP SCHEMA public CASCADE;
-- CREATE SCHEMA public;
-- GRANT ALL ON SCHEMA public TO public;

-- (no-op: rollback of baseline is intentionally a no-op for safety)
SELECT 'R001 rollback_init: no-op (baseline rollback requires manual intervention)' AS warning;
