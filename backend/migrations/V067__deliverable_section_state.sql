-- V067: 出品物章节级状态承载表 deliverable_section_state
-- Requirements: 4.4, 4.5
-- 身份键 word_export_task_id 绑 task 级（跨版本稳定），version_no 仅记录列不入唯一约束
-- 字段不绑死附注 doc_type，未来报表/报告正文出品物可复用同表
-- 所有 DDL 使用 IF NOT EXISTS，保证幂等可重入

-- ============================================================================
-- 1. deliverable_section_state: 章节 stale + 源快照 hash + 回填基线
--    TimestampMixin 列须显式写 created_at/updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- ============================================================================

CREATE TABLE IF NOT EXISTS deliverable_section_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    word_export_task_id UUID NOT NULL,
    version_no INT,
    project_id UUID NOT NULL,
    year INT NOT NULL,
    section_code VARCHAR(64) NOT NULL,
    source_snapshot_hash VARCHAR(64),
    is_stale BOOLEAN NOT NULL DEFAULT false,
    last_writeback_baseline_hash VARCHAR(64),
    anchor_name VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 2. 索引：唯一约束 + 查询优化
-- ============================================================================

-- 唯一约束：同一 task 下 section_code 唯一（跨版本稳定）
CREATE UNIQUE INDEX IF NOT EXISTS uq_deliverable_section
    ON deliverable_section_state (word_export_task_id, section_code);

-- 按项目+年度查询
CREATE INDEX IF NOT EXISTS idx_dss_project_year
    ON deliverable_section_state (project_id, year);

-- 按 task 查 stale 章节（增量刷新场景）
CREATE INDEX IF NOT EXISTS idx_dss_stale
    ON deliverable_section_state (word_export_task_id, is_stale);

-- 按项目+年度+章节定位（溯源面板场景）
CREATE INDEX IF NOT EXISTS idx_dss_section
    ON deliverable_section_state (project_id, year, section_code);
