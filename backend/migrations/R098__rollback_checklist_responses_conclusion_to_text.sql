-- R098: 回滚 V098（conclusion TEXT -> VARCHAR(32)）。
DO $$
BEGIN
    IF to_regclass('public.checklist_responses') IS NOT NULL
       AND EXISTS (SELECT 1 FROM checklist_responses WHERE length(conclusion) > 32) THEN
        RAISE EXCEPTION 'R098 拒绝回滚：checklist_responses.conclusion 存在超过 32 字符的值';
    END IF;
END $$;
ALTER TABLE checklist_responses ALTER COLUMN conclusion TYPE VARCHAR(32);
