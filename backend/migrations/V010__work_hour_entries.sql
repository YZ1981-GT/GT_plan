-- V010: 新增 work_hour_entries 表（Phase 7 F7: 工时填报粒度细化）
-- 三级粒度：循环/底稿/程序

CREATE TABLE IF NOT EXISTS work_hour_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    project_id UUID NOT NULL REFERENCES projects(id),
    date DATE NOT NULL,
    hours DECIMAL(5,2) NOT NULL CHECK (hours > 0 AND hours <= 24),
    cycle VARCHAR(10) NOT NULL,
    wp_code VARCHAR(30),
    procedure VARCHAR(100),
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    submitted_at TIMESTAMP WITH TIME ZONE,
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP WITH TIME ZONE,
    rejected_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_whe_user_date ON work_hour_entries (user_id, date);
CREATE INDEX idx_whe_project_status ON work_hour_entries (project_id, status);
CREATE INDEX idx_whe_project_cycle ON work_hour_entries (project_id, cycle);

COMMENT ON TABLE work_hour_entries IS '工时填报条目（三级粒度：循环/底稿/程序）';
