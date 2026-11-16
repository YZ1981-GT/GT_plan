-- R135: 回滚 V135（reviewer_update action）。
-- 旧 CHECK 的完整合法值集合依赖迁移前 schema 快照；现有 reviewer_update 行也不能静默删除。
DO $$ BEGIN
    RAISE EXCEPTION 'R135 拒绝自动回滚：reviewer_update 约束值需按现有数据人工裁决';
END $$;
