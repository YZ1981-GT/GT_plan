-- R231: 回滚 V231。
-- V231 是破坏性删除迁移（contract_wp_link/contract_extracted/contracts 与枚举）。
-- 原始表/数据已删除，无法从当前库安全重建；必须使用 V231 前的备份恢复。
DO $$ BEGIN
    RAISE EXCEPTION 'R231 拒绝自动回滚：V231 已删除合同表/枚举，需从迁移前备份恢复';
END $$;
