-- R112: 回滚 V112（程序/行定义 revision registry）。
DO $$
BEGIN
    IF (to_regclass('public.procedure_template_revisions') IS NOT NULL AND EXISTS (SELECT 1 FROM procedure_template_revisions LIMIT 1))
       OR (to_regclass('public.procedure_row_definition_revisions') IS NOT NULL AND EXISTS (SELECT 1 FROM procedure_row_definition_revisions LIMIT 1)) THEN
        RAISE EXCEPTION 'R112 拒绝回滚：revision registry 存在版本链数据';
    END IF;
END $$;
DROP TABLE IF EXISTS procedure_row_definition_revisions;
DROP TABLE IF EXISTS procedure_template_revisions;
DO $$ BEGIN RAISE EXCEPTION 'R112 仍需人工恢复 procedure_row_task_history 的 append-only 触发器'; END $$;
