-- V040: ReportConfigBaseline 表 + report_config.is_stale 列
-- 报表配置主模板回填候选表（项目优化→主模板评审通道）

CREATE TABLE IF NOT EXISTS report_config_baseline (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    standard VARCHAR(40) NOT NULL,
    report_type VARCHAR(20) NOT NULL,
    row_code VARCHAR(40) NOT NULL,
    candidate_formula TEXT,
    source_project_id UUID,
    status VARCHAR(20) DEFAULT 'pending',
    version INT DEFAULT 1,
    submitted_by UUID,
    reviewed_by UUID,
    created_at TIMESTAMP DEFAULT now()
);

-- report_config 加 is_stale 列（主模板更新→克隆项目标脏）
ALTER TABLE report_config ADD COLUMN IF NOT EXISTS is_stale BOOLEAN DEFAULT false;
