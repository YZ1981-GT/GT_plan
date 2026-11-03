-- V230: 证据链接加凭证键（spec attachment-voucher-evidence-binding 需求 1，ADR-AVE-01）。
--
-- 凭证检查行的原件（记账凭证、发票、回单等）按凭证身份挂：同一张凭证被多张底稿抽到时，可以在别的底稿里
-- 查到已经取得的原件并引用。凭证键 = 年度 + 主体 + 日期 + 凭证字 + 凭证号的规范串（voucher_identity.VoucherKey）。
--   - 唯一索引带位置：按序号挂附件的表删行时「先建新位置、再删旧位置」，只按（底稿, 凭证, 附件）去重会撞上旧位置。
--   - 真库此表 0 行，不回填。
ALTER TABLE evidence_links ADD COLUMN IF NOT EXISTS voucher_key TEXT;
CREATE INDEX IF NOT EXISTS idx_evidence_links_voucher_key ON evidence_links (voucher_key)
    WHERE voucher_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_links_voucher_position ON evidence_links
    (wp_id, voucher_key, attachment_id, COALESCE(sheet_name, ''), COALESCE(cell_ref, ''))
    WHERE voucher_key IS NOT NULL;
