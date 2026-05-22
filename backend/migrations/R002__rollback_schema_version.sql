-- R002__rollback_schema_version.sql
-- 回滚 V002__add_schema_version.sql
-- 删除 schema_version 表（如果存在）

DROP TABLE IF EXISTS schema_version;
