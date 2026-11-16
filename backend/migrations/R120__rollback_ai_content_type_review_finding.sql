-- R120: 回滚 V120。
-- PostgreSQL 不支持 DROP ENUM VALUE；review_finding 可能已被 ai_content_log 使用，故有意拒绝自动回滚。
DO $$ BEGIN
    RAISE EXCEPTION 'R120 拒绝自动回滚：ai_content_type_enum 枚举值不可安全删除';
END $$;
