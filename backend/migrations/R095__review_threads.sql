-- R095: 回滚复核对话线程 + 消息表
-- 按依赖逆序删除：先 review_messages（FK 引用 review_threads），再 review_threads

DROP INDEX IF EXISTS ix_review_messages_created_at;
DROP INDEX IF EXISTS ix_review_messages_thread_id;
DROP TABLE IF EXISTS review_messages;

DROP INDEX IF EXISTS ix_review_threads_wp_id;
DROP INDEX IF EXISTS uix_review_threads_thread_key;
DROP TABLE IF EXISTS review_threads;
