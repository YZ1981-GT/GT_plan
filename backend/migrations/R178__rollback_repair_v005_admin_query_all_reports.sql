-- R178__rollback_repair_v005_admin_query_all_reports.sql
-- 回滚 V178：删除补齐的 admin bypass 函数（与 R005__disable_rls.sql 中的 DROP 一致）。

DROP FUNCTION IF EXISTS admin_query_all_reports();
