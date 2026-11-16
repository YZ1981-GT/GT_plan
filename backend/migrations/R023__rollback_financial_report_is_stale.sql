-- R023: 回滚 V023（financial_report.is_stale）。
DO $$
BEGIN
    IF to_regclass('public.financial_report') IS NOT NULL
       AND EXISTS (SELECT 1 FROM financial_report WHERE is_stale IS TRUE) THEN
        RAISE EXCEPTION 'R023 拒绝回滚：financial_report 存在 stale 判定事实';
    END IF;
END $$;
DROP INDEX IF EXISTS idx_financial_report_stale;
ALTER TABLE financial_report DROP COLUMN IF EXISTS is_stale;
