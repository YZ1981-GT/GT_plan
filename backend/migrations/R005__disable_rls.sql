-- R005__disable_rls.sql
-- 回滚 V005__enable_rls.sql
-- 禁用 RLS 并删除相关策略和函数

-- 1. 删除策略
DROP POLICY IF EXISTS project_isolation ON working_paper;
DROP POLICY IF EXISTS project_isolation ON adjustments;
DROP POLICY IF EXISTS project_isolation ON tb_balance;
DROP POLICY IF EXISTS project_isolation ON reports;
DROP POLICY IF EXISTS project_isolation ON review_records;

-- 2. 禁用 RLS
ALTER TABLE working_paper DISABLE ROW LEVEL SECURITY;
ALTER TABLE adjustments DISABLE ROW LEVEL SECURITY;
ALTER TABLE tb_balance DISABLE ROW LEVEL SECURITY;
ALTER TABLE reports DISABLE ROW LEVEL SECURITY;
ALTER TABLE review_records DISABLE ROW LEVEL SECURITY;

-- 3. 删除 bypass 函数
DROP FUNCTION IF EXISTS admin_query_all_working_papers();
DROP FUNCTION IF EXISTS admin_query_all_reports();

-- 4. 删除索引（保留也无害，但为完整回滚删除）
DROP INDEX IF EXISTS idx_working_paper_project_id;
DROP INDEX IF EXISTS idx_adjustments_project_id;
DROP INDEX IF EXISTS idx_tb_balance_project_id;
DROP INDEX IF EXISTS idx_reports_project_id;
