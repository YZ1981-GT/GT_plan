-- V232: 证据链接加合同键（Spec F FEAT-001 F2，镜像 V230 凭证键）。
--
-- 合同检查行的原件（合同原件、补充协议等）按合同身份挂：同一份合同被多张底稿引用时，
-- 可以在别的底稿里查到已经取得的原件并引用。合同键 = ['合同号','对方名称'] 的规范 JSON 串。
--   - 唯一索引带位置：与凭证键相同逻辑。
--   - 真库此表 0 行，不回填。
ALTER TABLE evidence_links ADD COLUMN IF NOT EXISTS contract_key TEXT;
CREATE INDEX IF NOT EXISTS idx_evidence_links_contract_key ON evidence_links (contract_key)
    WHERE contract_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_links_contract_position ON evidence_links
    (wp_id, contract_key, attachment_id, COALESCE(sheet_name, ''), COALESCE(cell_ref, ''))
    WHERE contract_key IS NOT NULL;
