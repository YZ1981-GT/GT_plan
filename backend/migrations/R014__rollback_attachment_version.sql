-- R014__rollback_attachment_version.sql
-- 回滚 V014__add_attachment_version.sql
-- 删除 attachments 表的 version + previous_version_id 字段及相关索引

DROP INDEX IF EXISTS idx_attachments_previous_version;
DROP INDEX IF EXISTS idx_attachments_version_chain;

ALTER TABLE attachments
    DROP COLUMN IF EXISTS previous_version_id;

ALTER TABLE attachments
    DROP COLUMN IF EXISTS version;
