-- R033: 回滚 V033。
-- V033 建立大量跨模块表并扩展多个既有表，没有迁移前 schema/数据快照时不能安全删除。
DO $$
BEGIN
    RAISE EXCEPTION 'R033 拒绝自动回滚：V033 包含知识库、QC、底稿、审计等跨模块 schema，请使用备份恢复';
END $$;
