-- V006__eqcr_snapshots.sql
-- Phase 4 F3: EQCR 快照机制
-- 创建 eqcr_snapshots 表，存储 EQCR 独立复核的项目快照数据
-- 快照数据以 JSONB 格式存储（底稿状态+报表数据+调整分录+VR结果）

CREATE TABLE eqcr_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    snapshot_data JSONB NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE
);

-- 唯一约束：同一项目同一年度只能有一个 is_current=TRUE 的快照
-- 使用 partial unique index 实现
CREATE UNIQUE INDEX idx_eqcr_snapshots_current
    ON eqcr_snapshots (project_id, year)
    WHERE is_current = TRUE;

-- 查询优化索引
CREATE INDEX idx_eqcr_snapshots_project_year
    ON eqcr_snapshots (project_id, year);

CREATE INDEX idx_eqcr_snapshots_created_at
    ON eqcr_snapshots (created_at DESC);

COMMENT ON TABLE eqcr_snapshots IS 'EQCR 独立复核快照 — 冻结项目数据供 EQCR 合伙人只读查看';
COMMENT ON COLUMN eqcr_snapshots.snapshot_data IS '全量快照 JSONB: {workpapers, reports, adjustments, vr_results, metadata}';
COMMENT ON COLUMN eqcr_snapshots.is_current IS '当前有效快照标记，同项目同年度仅一个 TRUE';
