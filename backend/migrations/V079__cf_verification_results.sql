-- CF 核查结果缓存表
CREATE TABLE IF NOT EXISTS cf_verification_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    check_type VARCHAR(50) NOT NULL,  -- 'cash_equivalents' | 'reconciliation' | 'main_table' | 'supplementary'
    item_code VARCHAR(20),            -- CFS-002 等，主表逆算各项对应的行号
    reported_amount NUMERIC(18,2),    -- 报表值
    calculated_amount NUMERIC(18,2),  -- 逆算值
    difference NUMERIC(18,2),         -- 差异
    pass BOOLEAN DEFAULT FALSE,       -- 是否通过（差异在容差内）
    explanation TEXT,                  -- 用户填写的差异说明
    result_data JSONB,                -- 详细计算过程（各组件值）
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, year, check_type, item_code)
);

CREATE INDEX IF NOT EXISTS idx_cf_verification_results_project_year
    ON cf_verification_results(project_id, year);

COMMENT ON TABLE cf_verification_results IS '现金流量表核查结果缓存+用户差异说明';
