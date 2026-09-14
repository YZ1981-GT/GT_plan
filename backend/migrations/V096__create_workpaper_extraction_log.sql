-- V096: 创建 workpaper_extraction_log 表
-- 存储截止测试/抽凭引擎的执行日志和填充前快照，支持审计留痕和撤销功能

CREATE TABLE IF NOT EXISTS workpaper_extraction_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    workpaper_id UUID NOT NULL REFERENCES working_paper(id),
    user_id UUID NOT NULL,
    extraction_type VARCHAR(50) NOT NULL,
    extraction_criteria JSONB NOT NULL,
    total_matched INTEGER NOT NULL,
    filled_count INTEGER NOT NULL,
    fill_mode VARCHAR(20) NOT NULL,
    before_data JSONB,
    is_undone BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_extraction_log_wp_created
    ON workpaper_extraction_log(workpaper_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_extraction_log_project
    ON workpaper_extraction_log(project_id);
