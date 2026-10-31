-- R230: 回滚 V230 —— 删凭证键的两个索引与列（列上的凭证身份随之丢失，链接本身保留）。
DROP INDEX IF EXISTS uq_evidence_links_voucher_position;
DROP INDEX IF EXISTS idx_evidence_links_voucher_key;
ALTER TABLE evidence_links DROP COLUMN IF EXISTS voucher_key;
