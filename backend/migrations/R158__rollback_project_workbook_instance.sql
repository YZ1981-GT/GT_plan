-- R158: 回滚 V158（项目工作簿实例/页签）。
DO $$
BEGIN
    IF (to_regclass('public.project_workbook_sheet_entry') IS NOT NULL AND EXISTS (SELECT 1 FROM project_workbook_sheet_entry LIMIT 1))
       OR (to_regclass('public.project_workbook_instance') IS NOT NULL AND EXISTS (SELECT 1 FROM project_workbook_instance LIMIT 1)) THEN
        RAISE EXCEPTION 'R158 拒绝回滚：工作簿/页签/entry 身份数据存在';
    END IF;
END $$;
DROP TABLE IF EXISTS project_workbook_sheet_entry;
DROP TABLE IF EXISTS project_workbook_instance;
