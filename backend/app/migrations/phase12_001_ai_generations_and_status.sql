-- Phase 12 Migration 001: AI生成留痕表 + 后台任务表 + 底稿状态字段
-- 执行时机：阶段2开始前
-- 回滚：phase12_001_rollback.sql

-- 1. wp_ai_generations 表
CREATE TABLE IF NOT EXISTS wp_ai_generations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wp_id UUID NOT NULL REFERENCES working_paper(id),
    prompt_version VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    input_hash VARCHAR(64),
    output_text TEXT,
    output_structured JSONB,
    status VARCHAR(30) NOT NULL DEFAULT 'drafted',
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    confirmed_by UUID REFERENCES users(id),
    confirmed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wp_ai_generations_wp
    ON wp_ai_generations(wp_id, created_at DESC);

-- 2. background_jobs 表
CREATE TABLE IF NOT EXISTS background_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    payload JSONB,
    progress_total INTEGER NOT NULL DEFAULT 0,
    progress_done INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    initiated_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_background_jobs_project
    ON background_jobs(project_id, created_at DESC);

-- 3. background_job_items 表
CREATE TABLE IF NOT EXISTS background_job_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES background_jobs(id),
    wp_id UUID NOT NULL REFERENCES working_paper(id),
    status VARCHAR(30) NOT NULL,
    error_message TEXT,
    finished_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_background_job_items_job
    ON background_job_items(job_id, status);

-- 4. working_paper 新增状态字段
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS workflow_status VARCHAR(30) DEFAULT 'draft';
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS explanation_status VARCHAR(30) DEFAULT 'not_started';
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS consistency_status VARCHAR(30) DEFAULT 'unknown';
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS last_parsed_sync_at TIMESTAMP;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS partner_reviewed_at TIMESTAMP;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS partner_reviewed_by UUID REFERENCES users(id);

-- 5. wp_recommendation_feedback 表
CREATE TABLE IF NOT EXISTS wp_recommendation_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_code VARCHAR(50) NOT NULL,
    action VARCHAR(30) NOT NULL,
    action_by UUID REFERENCES users(id),
    action_at TIMESTAMP DEFAULT NOW(),
    project_type VARCHAR(50),
    industry VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_wp_feedback_project ON wp_recommendation_feedback(project_id);
CREATE INDEX IF NOT EXISTS idx_wp_feedback_action ON wp_recommendation_feedback(action, action_at);

-- 6. wp_edit_sessions 表
CREATE TABLE IF NOT EXISTS wp_edit_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wp_id UUID NOT NULL REFERENCES working_paper(id),
    user_id UUID NOT NULL REFERENCES users(id),
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    duration_seconds INTEGER,
    source VARCHAR(30) NOT NULL DEFAULT 'wopi'
);
