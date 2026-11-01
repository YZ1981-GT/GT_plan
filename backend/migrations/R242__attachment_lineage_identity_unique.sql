-- 回退仅移除新增唯一索引，不删除任何溯源数据。
DROP INDEX IF EXISTS uq_attachment_lineage_identity;
