-- R150: 回滚 V150（AI chat message seq）。
-- 历史 seq 已回填，无法无损恢复 NULL；有消息时拒绝删除序列/默认值。
DO $$
BEGIN
    IF to_regclass('public.ai_chat_message') IS NOT NULL
       AND EXISTS (SELECT 1 FROM ai_chat_message WHERE seq IS NOT NULL) THEN
        RAISE EXCEPTION 'R150 拒绝回滚：ai_chat_message.seq 已回填/使用';
    END IF;
END $$;
ALTER TABLE ai_chat_message ALTER COLUMN seq DROP DEFAULT;
ALTER TABLE ai_chat_message ALTER COLUMN seq DROP NOT NULL;
DROP SEQUENCE IF EXISTS ai_chat_message_seq_seq;
