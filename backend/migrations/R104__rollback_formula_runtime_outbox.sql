-- R104: 回滚 V104（公式 runtime outbox 与刷新审计扩展）。
DO $$
BEGIN
    IF (to_regclass('public.formula_runtime_outbox') IS NOT NULL AND EXISTS (SELECT 1 FROM formula_runtime_outbox LIMIT 1))
       OR (to_regclass('public.draft_refresh_audit') IS NOT NULL AND EXISTS (SELECT 1 FROM draft_refresh_audit LIMIT 1))
       OR (to_regclass('public.draft_refresh_snapshot') IS NOT NULL AND EXISTS (SELECT 1 FROM draft_refresh_snapshot LIMIT 1)) THEN
        RAISE EXCEPTION 'R104 拒绝回滚：公式 outbox/刷新审计或快照存在数据';
    END IF;
END $$;
DROP TABLE IF EXISTS formula_runtime_outbox;
ALTER TABLE draft_refresh_audit DROP COLUMN IF EXISTS failure_detail;
ALTER TABLE draft_refresh_audit DROP COLUMN IF EXISTS after_version;
ALTER TABLE draft_refresh_audit DROP COLUMN IF EXISTS before_version;
ALTER TABLE draft_refresh_audit DROP COLUMN IF EXISTS target_locator;
ALTER TABLE draft_refresh_audit DROP COLUMN IF EXISTS transaction_mode;
ALTER TABLE draft_refresh_audit DROP COLUMN IF EXISTS revision_fingerprint;
ALTER TABLE draft_refresh_snapshot DROP COLUMN IF EXISTS restored_at;
ALTER TABLE draft_refresh_snapshot DROP COLUMN IF EXISTS after_version;
ALTER TABLE draft_refresh_snapshot DROP COLUMN IF EXISTS before_version;
ALTER TABLE draft_refresh_snapshot DROP COLUMN IF EXISTS target_locator;
ALTER TABLE draft_refresh_snapshot DROP COLUMN IF EXISTS domain;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS definition_hash;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS definition_version;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS lifecycle_state;
