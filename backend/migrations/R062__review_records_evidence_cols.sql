-- R062: 回滚 review_records 复核证据链字段
ALTER TABLE review_records DROP COLUMN IF EXISTS evidence_refs;
ALTER TABLE review_records DROP COLUMN IF EXISTS close_reason;
ALTER TABLE review_records DROP COLUMN IF EXISTS close_evidence_refs;
