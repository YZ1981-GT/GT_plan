-- V005: 启用 PG RLS 行级安全（Phase 4 F1）
-- 注意：仅对已存在的表执行，使用 IF NOT EXISTS 保护

-- 1. working_paper RLS
ALTER TABLE working_paper ENABLE ROW LEVEL SECURITY;
ALTER TABLE working_paper FORCE ROW LEVEL SECURITY;

-- 2. adjustments RLS
ALTER TABLE adjustments ENABLE ROW LEVEL SECURITY;
ALTER TABLE adjustments FORCE ROW LEVEL SECURITY;

-- 3. tb_balance RLS
ALTER TABLE tb_balance ENABLE ROW LEVEL SECURITY;
ALTER TABLE tb_balance FORCE ROW LEVEL SECURITY;

-- 4. review_records RLS
ALTER TABLE review_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_records FORCE ROW LEVEL SECURITY;

-- 5. 索引
CREATE INDEX IF NOT EXISTS idx_working_paper_project_id ON working_paper (project_id);
CREATE INDEX IF NOT EXISTS idx_adjustments_project_id ON adjustments (project_id);
CREATE INDEX IF NOT EXISTS idx_tb_balance_project_id ON tb_balance (project_id);
