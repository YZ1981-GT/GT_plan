-- V017__v3_refinement_tables.sql
-- V3 收官增强：创建 3 张新表 + 索引
-- ai_content_log (Req 6 AI 内容溯源)
-- cross_module_conflicts (Req 7 跨模块冲突调解)
-- time_machine_snapshots (Req 11 时光机)

-- ============================================================
-- 1. ai_content_log — AI 生成内容溯源日志
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_content_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_id UUID,
    user_id UUID NOT NULL REFERENCES users(id),
    content_hash VARCHAR(64) NOT NULL,
    target_cell VARCHAR(255),
    prompt_hash VARCHAR(64),
    model VARCHAR(100) NOT NULL,
    confidence NUMERIC(5,4),
    generated_content TEXT NOT NULL,
    revised_content TEXT,
    confirm_action VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (confirm_action IN ('pending', 'confirmed', 'revised', 'rejected')),
    confirmed_by UUID REFERENCES users(id),
    confirmed_at TIMESTAMPTZ,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ai_content_log IS 'AI 生成内容溯源日志 — 字段级追踪 AI 输出及人工确认状态';
COMMENT ON COLUMN ai_content_log.content_hash IS 'SHA-256 of generated_content，用于去重与溯源';
COMMENT ON COLUMN ai_content_log.target_cell IS '目标字段标识（字段级粒度），如 workpaper.cell_A1';
COMMENT ON COLUMN ai_content_log.confirm_action IS '确认动作：pending/confirmed/revised/rejected';

CREATE INDEX IF NOT EXISTS idx_ai_content_log_project
    ON ai_content_log (project_id);

CREATE INDEX IF NOT EXISTS idx_ai_content_log_project_action
    ON ai_content_log (project_id, confirm_action);

CREATE INDEX IF NOT EXISTS idx_ai_content_log_wp
    ON ai_content_log (wp_id);

-- ============================================================
-- 2. cross_module_conflicts — 跨模块冲突调解记录
-- ============================================================
CREATE TABLE IF NOT EXISTS cross_module_conflicts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    source_module VARCHAR(50) NOT NULL,
    source_id UUID NOT NULL,
    target_module VARCHAR(50) NOT NULL,
    target_id UUID NOT NULL,
    target_field VARCHAR(100) NOT NULL,
    upstream_value TEXT,
    manual_value TEXT,
    final_value TEXT,
    resolution VARCHAR(20)
        CHECK (resolution IN ('keep_manual', 'accept_new', 'merge')),
    resolved_by UUID REFERENCES users(id),
    resolved_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'resolved', 'auto_skipped')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE cross_module_conflicts IS '跨模块冲突调解记录 — 上游数据变更与手工覆盖的冲突追踪';
COMMENT ON COLUMN cross_module_conflicts.source_module IS '冲突来源模块（如 trial_balance / adjustment）';
COMMENT ON COLUMN cross_module_conflicts.target_field IS '目标字段名（如 amount / description）';
COMMENT ON COLUMN cross_module_conflicts.resolution IS '解决方式：keep_manual/accept_new/merge';

CREATE INDEX IF NOT EXISTS idx_cross_module_conflicts_project_status
    ON cross_module_conflicts (project_id, status);

CREATE INDEX IF NOT EXISTS idx_cross_module_conflicts_target
    ON cross_module_conflicts (target_module, target_id, target_field);

-- ============================================================
-- 3. time_machine_snapshots — 时光机增量快照
-- ============================================================
CREATE TABLE IF NOT EXISTS time_machine_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id UUID NOT NULL,
    instance_type VARCHAR(50) NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    project_id UUID NOT NULL REFERENCES projects(id),
    diff_json JSONB NOT NULL,
    parent_snapshot_id UUID REFERENCES time_machine_snapshots(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE time_machine_snapshots IS '时光机增量快照 — RFC 6902 JSON Patch 反向 diff';
COMMENT ON COLUMN time_machine_snapshots.instance_type IS '实例类型：workpaper/adjustment/disclosure 等';
COMMENT ON COLUMN time_machine_snapshots.diff_json IS 'RFC 6902 JSON Patch 格式的反向 diff';
COMMENT ON COLUMN time_machine_snapshots.parent_snapshot_id IS '父快照 ID，形成链式历史';

CREATE INDEX IF NOT EXISTS idx_time_machine_snapshots_instance
    ON time_machine_snapshots (instance_type, instance_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_time_machine_snapshots_project
    ON time_machine_snapshots (project_id, created_at DESC);
