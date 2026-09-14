-- R065: 回滚 processing enum value
-- 注意：PostgreSQL 不支持 ALTER TYPE DROP VALUE，
-- 只能通过重建 enum 实现回滚（风险高，正常不执行）
-- 此回滚文件为占位，实际回滚需手动处理

-- NO-OP: PG 不支持 ALTER TYPE DROP VALUE
SELECT 1;
