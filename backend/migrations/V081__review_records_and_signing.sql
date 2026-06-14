-- 复核检查表记录
CREATE TABLE IF NOT EXISTS review_checklist_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    template_code VARCHAR(10) NOT NULL,
    reviewer_id UUID NOT NULL REFERENCES users(id),
    items JSONB NOT NULL DEFAULT '[]',
    opinion TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, year, template_code, reviewer_id)
);

CREATE INDEX IF NOT EXISTS idx_review_checklist_records_project_year
    ON review_checklist_records(project_id, year);

COMMENT ON TABLE review_checklist_records IS '复核检查表记录（A21~A25 各级勾选+意见）';

-- 独立性签署任务表
CREATE TABLE IF NOT EXISTS independence_signing_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    template_code VARCHAR(10) NOT NULL DEFAULT 'A17-7',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    signed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, user_id, template_code)
);

CREATE INDEX IF NOT EXISTS idx_independence_signing_project
    ON independence_signing_tasks(project_id);

COMMENT ON TABLE independence_signing_tasks IS 'A17-7 独立性声明书电子签署任务';
