-- V062: review_records 复核证据链字段
-- 关联 Spec: platform-evidence-knowledge-ai-governance P1-1（复核意见证据链）

ALTER TABLE review_records ADD COLUMN IF NOT EXISTS evidence_refs JSONB;
ALTER TABLE review_records ADD COLUMN IF NOT EXISTS close_reason TEXT;
ALTER TABLE review_records ADD COLUMN IF NOT EXISTS close_evidence_refs JSONB;

COMMENT ON COLUMN review_records.evidence_refs IS '复核意见关联的证据引用列表 (EvidenceRef[])';
COMMENT ON COLUMN review_records.close_reason IS '关闭复核意见时填写的关闭依据';
COMMENT ON COLUMN review_records.close_evidence_refs IS '关闭时关联的证据引用列表 (EvidenceRef[])';
