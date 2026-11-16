-- R113: 回滚 V113（AI content governance）。
DO $$
BEGIN
    IF to_regclass('public.ai_content_governance') IS NOT NULL
       AND EXISTS (SELECT 1 FROM ai_content_governance LIMIT 1) THEN
        RAISE EXCEPTION 'R113 拒绝回滚：AI 内容治理生命周期/确认/版本链数据存在';
    END IF;
END $$;
DROP TABLE IF EXISTS ai_content_governance;
