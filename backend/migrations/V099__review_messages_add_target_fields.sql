-- V099: review_messages 增加定向复核字段（指定人/角色）

ALTER TABLE review_messages
    ADD COLUMN IF NOT EXISTS target_user_id UUID NULL REFERENCES users(id);

ALTER TABLE review_messages
    ADD COLUMN IF NOT EXISTS target_user_name VARCHAR(120) NULL;

ALTER TABLE review_messages
    ADD COLUMN IF NOT EXISTS target_role VARCHAR(50) NULL;

CREATE INDEX IF NOT EXISTS ix_review_messages_target_user_id
    ON review_messages(target_user_id);
