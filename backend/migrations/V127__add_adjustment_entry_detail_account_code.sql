-- V127: adjustment_entries 表增加 detail_account_code 列（调整分录明细科目码）
-- spec: adjustment-detail-account-code
--   detail_account_code — 审计师原始选定的明细/二级科目码（如 112201），可空。
--     NULL = 无更细明细，按一级 standard_account_code 处理（历史行为）。
-- 目的：standard_account_code（一级）继续用于科目校验/试算表 recalc/报表（零变更），
--   明细码仅用于把调整分录精确推送到底稿明细表/审定表。
-- 幂等：information_schema.columns 检测列存在性；additive，旧数据默认 NULL。
-- 零影响保证：recalc 从 adjustments 头表 account_code 聚合，不读本明细行表。

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'adjustment_entries' AND column_name = 'detail_account_code') THEN
    ALTER TABLE adjustment_entries ADD COLUMN detail_account_code VARCHAR;
  END IF;
END $$;
