-- R016: 回滚 V016（知识库文档版本列与索引）
-- 仅在新列仍为默认/空值时回滚，避免丢失版本链事实。
DO $$
BEGIN
    IF to_regclass('public.knowledge_documents') IS NOT NULL
       AND EXISTS (SELECT 1 FROM knowledge_documents WHERE version <> 1 OR previous_version_id IS NOT NULL) THEN
        RAISE EXCEPTION 'R016 拒绝回滚：knowledge_documents 已存在非默认版本链数据';
    END IF;
END $$;
DROP INDEX IF EXISTS idx_kb_documents_version_chain;
DROP INDEX IF EXISTS idx_kb_documents_previous_version;
ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS previous_version_id;
ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS version;
