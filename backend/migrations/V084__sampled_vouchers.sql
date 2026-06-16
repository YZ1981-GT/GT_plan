-- V084: 抽样凭证表（抽凭联动）
-- 用户在凭证穿透视图点击"抽中本凭证"→记录到此表，作为抽凭的样本清单。
-- 后续可关联到 sampling_records（统计层）或 working_paper（底稿层）。

CREATE TABLE IF NOT EXISTS sampled_vouchers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    year INTEGER NOT NULL,
    voucher_no VARCHAR(100) NOT NULL,
    account_code VARCHAR(50),
    -- 抽样上下文（可选关联）
    sampling_record_id UUID,
    working_paper_id UUID,
    note TEXT,
    -- 审计字段
    sampled_by UUID REFERENCES users(id),
    sampled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 同项目+年度+凭证号去重（同一凭证只抽一次）
CREATE UNIQUE INDEX IF NOT EXISTS uq_sampled_voucher_project_year_no
    ON sampled_vouchers (project_id, year, voucher_no)
    WHERE is_deleted = false;

CREATE INDEX IF NOT EXISTS idx_sampled_vouchers_project_year
    ON sampled_vouchers (project_id, year);
