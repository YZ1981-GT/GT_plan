-- R099: 回滚 V099（review_messages 定向字段）。
DO $$
BEGIN
    IF to_regclass('public.review_messages') IS NOT NULL
       AND EXISTS (SELECT 1 FROM review_messages WHERE target_user_id IS NOT NULL OR target_user_name IS NOT NULL OR target_role IS NOT NULL) THEN
        RAISE EXCEPTION 'R099 拒绝回滚：review_messages 已保存定向复核对象数据';
    END IF;
END $$;
DROP INDEX IF EXISTS ix_review_messages_target_user_id;
ALTER TABLE review_messages DROP COLUMN IF EXISTS target_role;
ALTER TABLE review_messages DROP COLUMN IF EXISTS target_user_name;
ALTER TABLE review_messages DROP COLUMN IF EXISTS target_user_id;
