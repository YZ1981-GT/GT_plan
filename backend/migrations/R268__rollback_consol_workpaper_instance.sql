-- R268：回滚合并薄底稿壳实例表。
-- 注意：仅回滚 schema；A3-CONSOL 的 WpIndex/WorkingPaper 壳与物理 artifact 文件不在此删除，
-- 由运维按底稿回收站与归档清单单独处理，避免误删审计底稿。

DROP INDEX IF EXISTS ux_consol_workpaper_instance_working_paper;
DROP INDEX IF EXISTS ux_consol_workpaper_instance_project_year;

DROP TABLE IF EXISTS consol_workpaper_instance;
