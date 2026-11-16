-- R110: 回滚 V110（V105/V110 修复登记与 retry 列）。
-- V110 只是修复/重放 V105 并新增 retry 时间，缺少迁移前 schema_version 与数据快照时不能安全反向删除。
DO $$ BEGIN
    RAISE EXCEPTION 'R110 拒绝自动回滚：V110 是程序行任务修复/重放迁移，请使用备份恢复';
END $$;
