-- R018: 回滚 V018（schema drift 大修）。
-- V018 同时建立/扩展大量业务对象，缺少迁移前 schema 快照时不能安全逆向；明确拒绝，
-- 保证 MigrationRunner 不会误删项目、审计、事件和快照数据。
DO $$
BEGIN
    RAISE EXCEPTION 'R018 拒绝自动回滚：V018 包含多表/多列 schema drift 修复，请使用迁移前备份人工恢复';
END $$;
