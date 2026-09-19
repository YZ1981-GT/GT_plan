-- R096: 回滚 workpaper_extraction_log 表

DROP INDEX IF EXISTS idx_extraction_log_project;
DROP INDEX IF EXISTS idx_extraction_log_wp_created;
DROP TABLE IF EXISTS workpaper_extraction_log;
