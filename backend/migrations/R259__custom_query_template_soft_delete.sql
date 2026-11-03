-- R214: 回滚 V214 —— 去掉 scope 检查约束、列表索引与软删两列。
-- 已软删（在回收站里）的模板会随 is_deleted 列一起「复活」：回滚前若要保留删除结果，先在回收站彻底删除。
ALTER TABLE custom_query_templates DROP CONSTRAINT IF EXISTS ck_custom_query_templates_scope;
DROP INDEX IF EXISTS idx_cqt_live_updated;
ALTER TABLE custom_query_templates DROP COLUMN IF EXISTS deleted_at, DROP COLUMN IF EXISTS is_deleted;
