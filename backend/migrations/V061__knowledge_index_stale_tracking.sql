-- V059: 知识库索引 stale 追踪字段
-- 关联 ADR: ADR-031-knowledge-base-source-of-truth-and-index-lifecycle
-- 关联 Spec: platform-evidence-knowledge-ai-governance P2-2

ALTER TABLE knowledge_index ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE knowledge_index ADD COLUMN IF NOT EXISTS doc_version INTEGER;

COMMENT ON COLUMN knowledge_index.is_stale IS '索引是否已过期（文档更新后旧索引标记为 stale）';
COMMENT ON COLUMN knowledge_index.doc_version IS '索引对应的文档版本号（关联 knowledge_documents.version）';
