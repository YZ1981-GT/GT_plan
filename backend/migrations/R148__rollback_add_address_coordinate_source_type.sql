-- R148: 回滚 V148。
-- PostgreSQL 不支持 DROP ENUM VALUE；address_coordinate 可能已被 ACNR 数据使用，拒绝自动重建。
DO $$ BEGIN
    RAISE EXCEPTION 'R148 拒绝自动回滚：knowledge_source_type_enum 枚举值不可安全删除';
END $$;
