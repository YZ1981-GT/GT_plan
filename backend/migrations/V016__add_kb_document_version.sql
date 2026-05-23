-- V016__add_kb_document_version.sql
-- AT-3 接入扩展：knowledge_documents 加 version + previous_version_id
-- 与 V014 attachment 版本管理同款契约
--
-- 版本链规则：
--   - 同 (folder_id, name) 第二次上传：version=N+1，previous_version_id 指向旧版本
--   - 旧版本保留（is_deleted=false）
--   - 跨链回滚被拒绝（attachment_id 与 version_id 必须同 folder_id + name）

ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS previous_version_id UUID;

CREATE INDEX IF NOT EXISTS idx_kb_documents_version_chain
    ON knowledge_documents (folder_id, name)
    WHERE is_deleted = false;

CREATE INDEX IF NOT EXISTS idx_kb_documents_previous_version
    ON knowledge_documents (previous_version_id)
    WHERE previous_version_id IS NOT NULL;

COMMENT ON COLUMN knowledge_documents.version
    IS 'AT-3 KB 文档版本号：同一 (folder_id, name) 下从 1 递增';
COMMENT ON COLUMN knowledge_documents.previous_version_id
    IS 'AT-3 上一版本 knowledge_documents.id；version=1 时为 NULL';
