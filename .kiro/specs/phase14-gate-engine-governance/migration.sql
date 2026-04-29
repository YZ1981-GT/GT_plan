-- Phase 14 migration: trace_events + gate_decisions
-- 对齐 v2 5.9.3 D-01/D-02
BEGIN;

-- 统一过程留痕主表（对齐 v2 WP-ENT-01 / 5.9.3 D-01 / 4.5.6 留痕清单）
CREATE TABLE IF NOT EXISTS trace_events (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    event_type VARCHAR(64) NOT NULL,       -- wp_saved/submit_review/sign_off/export/trim_applied/trim_rollback/gate_evaluated/sod_checked/review_returned/partner_signed
    object_type VARCHAR(32) NOT NULL,      -- workpaper/adjustment/report/note/procedure/conversation/export
    object_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    actor_role VARCHAR(32),                -- assistant/manager/partner/qc/admin
    action VARCHAR(100) NOT NULL,
    decision VARCHAR(16),                  -- allow/block/warn（门禁/SoD场景）
    reason_code VARCHAR(64),               -- 对齐 v2 4.5.6 统一原因码
    from_status VARCHAR(32),               -- 状态流转：起始状态（对齐 v2 4.5.6）
    to_status VARCHAR(32),                 -- 状态流转：目标状态
    before_snapshot JSONB,
    after_snapshot JSONB,
    content_hash VARCHAR(64),              -- 对象内容 SHA-256（取证用）
    version_no INT,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trace_events_project ON trace_events(project_id, event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trace_events_object ON trace_events(object_type, object_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trace_events_trace_id ON trace_events(trace_id);
CREATE INDEX IF NOT EXISTS idx_trace_events_actor ON trace_events(actor_id, created_at DESC);

-- 门禁决策记录表（对齐 v2 5.9.3 D-02）
CREATE TABLE IF NOT EXISTS gate_decisions (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    wp_id UUID NULL,
    gate_type VARCHAR(32) NOT NULL,        -- submit_review/sign_off/export_package
    decision VARCHAR(16) NOT NULL,         -- allow/warn/block
    hit_rules JSONB NOT NULL,              -- [{rule_code, error_code, severity, message, location, suggested_action}]
    actor_id UUID NOT NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gate_decisions_project_gate ON gate_decisions(project_id, gate_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gate_decisions_trace ON gate_decisions(trace_id);

COMMIT;
