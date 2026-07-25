-- R127: 回滚 V127 —— 删除 adjustment_entries.detail_account_code 列
-- spec: adjustment-detail-account-code
-- 幂等：列存在才删除。additive 列，删除不影响 standard_account_code 及下游。

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'adjustment_entries' AND column_name = 'detail_account_code') THEN
    ALTER TABLE adjustment_entries DROP COLUMN detail_account_code;
  END IF;
END $$;
