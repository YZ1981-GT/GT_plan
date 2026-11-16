-- R103: 回滚 V103（ACNR 项目覆盖）。
DO $$
BEGIN
    IF to_regclass('public.acnr_project_overlay') IS NOT NULL
       AND EXISTS (SELECT 1 FROM acnr_project_overlay LIMIT 1) THEN
        RAISE EXCEPTION 'R103 拒绝回滚：ACNR 项目覆盖数据存在';
    END IF;
END $$;
DROP INDEX IF EXISTS idx_acnr_overlay_project;
DROP TABLE IF EXISTS acnr_project_overlay;
