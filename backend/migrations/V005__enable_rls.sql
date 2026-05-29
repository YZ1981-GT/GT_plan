-- V005: 启用 PG RLS 行级安全（Phase 4 F1）
--
-- 设计要点（design.md F1）：
-- 1. SET LOCAL 仅在当前事务内有效，事务结束自动清除（安全）
-- 2. 不需要修改现有查询（RLS 透明过滤）
-- 3. admin bypass 通过 SECURITY DEFINER 函数实现（不需要 BYPASSRLS 角色）
-- 4. 应用角色不是表 owner，需要 FORCE ROW LEVEL SECURITY
--
-- 应用层 set_rls_context 必须用 set_config('app.current_project_id', value, true)
-- 而非 SET LOCAL ... = $1（PG 的 SET 命令不支持 prepared statement 绑定参数）

-- 1. 启用 RLS（ENABLE + FORCE，幂等保护）
ALTER TABLE working_paper ENABLE ROW LEVEL SECURITY;
ALTER TABLE working_paper FORCE ROW LEVEL SECURITY;

ALTER TABLE adjustments ENABLE ROW LEVEL SECURITY;
ALTER TABLE adjustments FORCE ROW LEVEL SECURITY;

ALTER TABLE tb_balance ENABLE ROW LEVEL SECURITY;
ALTER TABLE tb_balance FORCE ROW LEVEL SECURITY;

ALTER TABLE review_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_records FORCE ROW LEVEL SECURITY;

-- 2. 创建 project_isolation 策略（DROP 再 CREATE 保证幂等）
DROP POLICY IF EXISTS project_isolation ON working_paper;
CREATE POLICY project_isolation ON working_paper
  USING (project_id::text = current_setting('app.current_project_id', true));

DROP POLICY IF EXISTS project_isolation ON adjustments;
CREATE POLICY project_isolation ON adjustments
  USING (project_id::text = current_setting('app.current_project_id', true));

DROP POLICY IF EXISTS project_isolation ON tb_balance;
CREATE POLICY project_isolation ON tb_balance
  USING (project_id::text = current_setting('app.current_project_id', true));

-- review_records 通过 working_paper 间接关联项目
DROP POLICY IF EXISTS project_isolation ON review_records;
CREATE POLICY project_isolation ON review_records
  USING (working_paper_id IN (
    SELECT id FROM working_paper
    WHERE project_id::text = current_setting('app.current_project_id', true)
  ));

-- 3. admin bypass 函数（SECURITY DEFINER 绕过 RLS 跨项目查询用）
-- 注：函数体使用单行 SQL 避免 dollar quoting 与 SQLAlchemy text() 绑定参数冲突
CREATE OR REPLACE FUNCTION admin_query_all_working_papers()
RETURNS SETOF working_paper
LANGUAGE sql SECURITY DEFINER
AS 'SELECT * FROM working_paper WHERE is_deleted = false';

CREATE OR REPLACE FUNCTION admin_query_all_reports()
RETURNS SETOF financial_report
LANGUAGE sql SECURITY DEFINER
AS 'SELECT * FROM financial_report WHERE is_deleted = false';

-- 4. project_id 索引（RLS 谓词性能保障）
CREATE INDEX IF NOT EXISTS idx_working_paper_project_id ON working_paper (project_id);
CREATE INDEX IF NOT EXISTS idx_adjustments_project_id ON adjustments (project_id);
CREATE INDEX IF NOT EXISTS idx_tb_balance_project_id ON tb_balance (project_id);
