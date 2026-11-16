-- R101: 回滚 V101（高级查询模板项目共享范围）。
DO $$
BEGIN
    IF to_regclass('public.custom_query_templates') IS NOT NULL
       AND EXISTS (SELECT 1 FROM custom_query_templates WHERE cardinality(shared_project_ids) > 0) THEN
        RAISE EXCEPTION 'R101 拒绝回滚：模板已保存项目共享范围';
    END IF;
END $$;
DROP INDEX IF EXISTS idx_cqt_shared_projects;
ALTER TABLE custom_query_templates DROP COLUMN IF EXISTS shared_project_ids;
