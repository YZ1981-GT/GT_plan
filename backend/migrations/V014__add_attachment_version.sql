-- V014__add_attachment_version.sql
-- AT-3 附件版本管理（spec proposal-remaining-18 task 5.3）
-- attachments 表新增 version + previous_version_id 字段，用于同名文件的历史版本链
--
-- 版本链规则：
--   - 第一次上传 (project_id, reference_id, reference_type, file_name) 组合时，version=1, previous_version_id=NULL
--   - 同组合再次上传时：新建 attachment 行，version=max(version)+1，previous_version_id 指向旧版本
--   - 旧版本保留（is_deleted=false），不真删，仅前端"列出版本链"用
--   - 回滚：复制指定历史版本的文件路径/OCR 数据，新建 version=N+1 的 attachment，previous_version_id 指向当前最新版本

ALTER TABLE attachments
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE attachments
    ADD COLUMN IF NOT EXISTS previous_version_id UUID;

-- 索引：按 project_id + reference + file_name 快速查同名文件历史
CREATE INDEX IF NOT EXISTS idx_attachments_version_chain
    ON attachments (project_id, reference_id, reference_type, file_name)
    WHERE is_deleted = false;

CREATE INDEX IF NOT EXISTS idx_attachments_previous_version
    ON attachments (previous_version_id)
    WHERE previous_version_id IS NOT NULL;

COMMENT ON COLUMN attachments.version
    IS 'AT-3 附件版本号：同一 (project_id, reference_id, reference_type, file_name) 下从 1 递增';
COMMENT ON COLUMN attachments.previous_version_id
    IS 'AT-3 上一版本 attachment.id；version=1 时为 NULL；逻辑外键不强制（保留软删除链）';
