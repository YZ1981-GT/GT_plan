-- R176：回滚 V176
-- 注意：删除 wp_adjustment 会丢失历史底稿发布增量，执行前必须确认已完成备份。

ALTER TABLE trial_balance
    DROP COLUMN IF EXISTS wp_published_at;

ALTER TABLE trial_balance
    DROP COLUMN IF EXISTS wp_publish_base;

ALTER TABLE trial_balance
    DROP COLUMN IF EXISTS wp_adjustment;
