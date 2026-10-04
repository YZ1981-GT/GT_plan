-- V178__repair_v005_admin_query_all_reports.sql
-- 补齐 V005 缺失的 admin bypass 函数 admin_query_all_reports()。
--
-- 背景（见 checksum-drift-8 调查报告）：
--   V005 应用时跑的是一个未提交的中间版本，只建了 4 条 project_isolation 策略与第一个
--   bypass 函数 admin_query_all_working_papers()；当前磁盘 V005__enable_rls.sql 虽然声明了
--   admin_query_all_reports()，但因版本号 005 已登记为「已应用」，该声明从未被 runner 执行，
--   真库 pg_proc 中确实缺失此函数。
--   本迁移按 V005 现声明字节一致地补齐该 SECURITY DEFINER 函数。
--   admin_query_all_working_papers() 已在库，不重建（CREATE OR REPLACE 本身幂等，重建亦无害）。

CREATE OR REPLACE FUNCTION admin_query_all_reports()
RETURNS SETOF financial_report
LANGUAGE sql SECURITY DEFINER
AS 'SELECT * FROM financial_report WHERE is_deleted = false';
