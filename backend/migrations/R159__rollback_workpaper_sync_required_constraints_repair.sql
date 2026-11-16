-- R159: 回滚 V159。
-- V159 修复幂等、状态机和外键约束；删除这些保护会恢复已知漂移，且约束名依赖当时 schema 快照。
DO $$ BEGIN
    RAISE EXCEPTION 'R159 拒绝自动回滚：workpaper sync required constraints repair 会恢复已知数据完整性缺口';
END $$;
