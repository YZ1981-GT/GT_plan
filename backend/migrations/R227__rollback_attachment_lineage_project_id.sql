-- R227: 回滚 V227（attachment_lineage.project_id）
-- 回滚后附件三端点与溯源附件子源按「列未就绪」返回 503（services/attachment_lineage_schema.py；
-- 进程内只缓存「已就绪」，已缓存的进程需重启才会改判）。
DROP INDEX IF EXISTS idx_attachment_lineage_project_target;
ALTER TABLE attachment_lineage DROP COLUMN IF EXISTS project_id;
