-- R198: 回滚 V198 —— 去掉知识库扫描件后台 OCR 状态列（已写回的 content_text 保留）。
DROP INDEX IF EXISTS ix_knowledge_documents_ocr_queue;
ALTER TABLE knowledge_documents DROP CONSTRAINT IF EXISTS ck_knowledge_documents_ocr_status;
ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS ocr_due_at;
ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS ocr_error;
ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS ocr_attempts;
ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS ocr_status;
