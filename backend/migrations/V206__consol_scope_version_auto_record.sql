-- V206: 合并企业树版本改为自动记录（spec consol-autotree-linkage-closure R1，用户 2026-10-26 拍板）
-- 计算不再要求用户确认合并范围；推送时自动记录树版本（confirmation_mode = 'auto'，记录触发人，取不到为系统 = NULL）。
-- 手动「记录为新版本」仍走原 CAS 确认接口（confirmation_mode = 'user'）。

ALTER TABLE consol_scope_confirmations ALTER COLUMN confirmed_by DROP NOT NULL;

ALTER TABLE consol_scope_confirmations
    ADD COLUMN IF NOT EXISTS confirmation_mode VARCHAR(10) NOT NULL DEFAULT 'user';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_consol_scope_confirmation_mode'
    ) THEN
        ALTER TABLE consol_scope_confirmations
            ADD CONSTRAINT ck_consol_scope_confirmation_mode CHECK (confirmation_mode IN ('user', 'auto'));
    END IF;
END
$$;
