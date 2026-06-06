-- R053: 回滚 V053（PG 不支持 DROP VALUE，仅作标记）
-- ALTER TYPE ... DROP VALUE 不存在，需重建枚举类型才能回滚
-- 实际回滚需要：CREATE TYPE new → ALTER COLUMN SET TYPE new → DROP old → RENAME
SELECT 1; -- no-op rollback marker
