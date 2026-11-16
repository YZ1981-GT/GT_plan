-- R105: 回滚 V105（程序行任务与事件/通知扩展）。
DO $$
BEGIN
    IF (to_regclass('public.procedure_row_definitions') IS NOT NULL AND EXISTS (SELECT 1 FROM procedure_row_definitions LIMIT 1))
       OR (to_regclass('public.procedure_row_tasks') IS NOT NULL AND EXISTS (SELECT 1 FROM procedure_row_tasks LIMIT 1))
       OR (to_regclass('public.procedure_row_task_history') IS NOT NULL AND EXISTS (SELECT 1 FROM procedure_row_task_history LIMIT 1))
       OR (to_regclass('public.procedure_operation_previews') IS NOT NULL AND EXISTS (SELECT 1 FROM procedure_operation_previews LIMIT 1)) THEN
        RAISE EXCEPTION 'R105 拒绝回滚：程序行任务/历史/预览数据存在';
    END IF;
END $$;
DROP TABLE IF EXISTS procedure_row_task_history;
DROP TABLE IF EXISTS procedure_row_tasks;
DROP TABLE IF EXISTS procedure_operation_previews;
DROP TABLE IF EXISTS procedure_row_definitions;
-- task_events/notifications 新增列属于共用审计链，无法在无迁移前快照时安全删除。
DO $$ BEGIN RAISE EXCEPTION 'R105 仍需人工处理 task_events/notifications 扩展列'; END $$;
