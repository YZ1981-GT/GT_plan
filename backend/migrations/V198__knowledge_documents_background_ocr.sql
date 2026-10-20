-- V198: 知识库扫描件后台 OCR 状态（spec dsh-kb-ocr-local-first-routing ADR-DKR-005）。
--
-- 上传时正文为空且可 OCR（PDF / 图片）的文档标 pending，由后台 worker 经统一 OCR 路由
-- （本机优先、服务器兜底）识别后写回 content_text；上传请求内不再做 OCR。
-- ocr_status：NULL = 不需要 / 不适用；pending 待识别；running 识别中；done 已写回正文；
--   empty 识别成功但没有文字；failed 失败（ocr_error 为中文原因）。
-- ocr_due_at：pending 时 = 下次可尝试时间（退避）；running 时 = 租约到期（过期可被重新认领）。
-- ocr_attempts：已认领次数；写回以它为围栏，只有当前租约持有者能落库。
-- 不回填存量文档：存量扫描件由用户按需「重新识别」。
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS ocr_status VARCHAR(16);
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS ocr_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS ocr_error TEXT;
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS ocr_due_at TIMESTAMPTZ;
ALTER TABLE knowledge_documents DROP CONSTRAINT IF EXISTS ck_knowledge_documents_ocr_status;
ALTER TABLE knowledge_documents ADD CONSTRAINT ck_knowledge_documents_ocr_status
    CHECK (ocr_status IS NULL OR ocr_status IN ('pending', 'running', 'done', 'empty', 'failed'));
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_ocr_queue
    ON knowledge_documents (ocr_due_at)
    WHERE ocr_status IN ('pending', 'running');
