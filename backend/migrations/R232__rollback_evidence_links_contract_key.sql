-- R232: 回滚 V232（evidence_links.contract_key）。
DO $$
BEGIN
    IF to_regclass('public.evidence_links') IS NOT NULL
       AND EXISTS (SELECT 1 FROM evidence_links WHERE contract_key IS NOT NULL) THEN
        RAISE EXCEPTION 'R232 拒绝回滚：evidence_links 已保存合同身份键';
    END IF;
END $$;
DROP INDEX IF EXISTS uq_evidence_links_contract_position;
DROP INDEX IF EXISTS idx_evidence_links_contract_key;
ALTER TABLE evidence_links DROP COLUMN IF EXISTS contract_key;
