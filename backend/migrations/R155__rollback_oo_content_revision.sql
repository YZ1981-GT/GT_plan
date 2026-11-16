-- R155: 回滚 V155（OnlyOffice 内容版本）。
DO $$
BEGIN
    IF to_regclass('public.working_paper_oo_content_revision') IS NOT NULL
       AND EXISTS (SELECT 1 FROM working_paper_oo_content_revision LIMIT 1) THEN
        RAISE EXCEPTION 'R155 拒绝回滚：OnlyOffice 内容版本记录存在';
    END IF;
END $$;
DROP TABLE IF EXISTS working_paper_oo_content_revision;
