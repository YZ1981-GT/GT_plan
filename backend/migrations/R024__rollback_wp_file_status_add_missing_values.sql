-- R024: 回滚 V024。
-- PostgreSQL 不支持 DROP ENUM VALUE；重建 wp_file_status 需要逐列转换并处理现有值，
-- 因此有意拒绝自动回滚，避免静默破坏底稿状态。
DO $$
BEGIN
    RAISE EXCEPTION 'R024 拒绝自动回滚：wp_file_status 枚举值不可安全删除，请离线重建枚举';
END $$;
