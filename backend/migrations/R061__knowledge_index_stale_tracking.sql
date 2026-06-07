-- R059: 回滚知识库索引 stale 追踪字段
ALTER TABLE knowledge_index DROP COLUMN IF EXISTS is_stale;
ALTER TABLE knowledge_index DROP COLUMN IF EXISTS doc_version;
