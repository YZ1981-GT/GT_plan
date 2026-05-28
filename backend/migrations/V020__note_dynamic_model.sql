-- V020__note_dynamic_model.sql
-- Sprint A.1：附注动态模型基础设施（D1-D7 + D6 + D11）
--
-- 变更内容：
--   1. disclosure_notes 加 4 列（is_empty / template_lineage / is_local_override / text_template_vars）
--   2. 新建 group_note_template_baseline 表（D6 集团附注模板基线）
--   3. 新建 note_section_version_tree 表（D11 章节版本树）
--
-- 遵循 D6 idempotent 原则：全部 ALTER/CREATE 用 IF NOT EXISTS 包裹，可重复执行。

BEGIN;

-- ============================================================================
-- 1. disclosure_notes 新增字段（A.1.3）
-- ============================================================================

-- is_empty：标记章节是否为空（auto_trim 用）
ALTER TABLE disclosure_notes
    ADD COLUMN IF NOT EXISTS is_empty BOOLEAN NOT NULL DEFAULT false;

-- template_lineage：模板继承链路 JSON（集团基线 → 子公司覆盖追踪）
ALTER TABLE disclosure_notes
    ADD COLUMN IF NOT EXISTS template_lineage JSONB NULL;

-- is_local_override：是否为本地覆盖（子公司覆盖集团基线时标 true）
ALTER TABLE disclosure_notes
    ADD COLUMN IF NOT EXISTS is_local_override BOOLEAN NOT NULL DEFAULT false;

-- text_template_vars：文字段落 Jinja 模板变量 JSON
ALTER TABLE disclosure_notes
    ADD COLUMN IF NOT EXISTS text_template_vars JSONB NULL;

-- ============================================================================
-- 2. group_note_template_baseline 表（A.1.4 / D6 集团附注模板基线）
-- ============================================================================

CREATE TABLE IF NOT EXISTS group_note_template_baseline (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    parent_project_id UUID NOT NULL REFERENCES projects(id),
    version VARCHAR(20) NOT NULL DEFAULT 'v1.0',
    parent_baseline_id UUID NULL REFERENCES group_note_template_baseline(id),
    template_type VARCHAR(20) NOT NULL DEFAULT 'soe',
    sections_data JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by UUID NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_group_baseline_parent_project
    ON group_note_template_baseline(parent_project_id);

CREATE INDEX IF NOT EXISTS ix_group_baseline_parent_baseline
    ON group_note_template_baseline(parent_baseline_id);

-- ============================================================================
-- 3. note_section_version_tree 表（A.1.5 / D11 章节版本树）
-- ============================================================================

CREATE TABLE IF NOT EXISTS note_section_version_tree (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    note_section_id VARCHAR(100) NOT NULL,
    branch VARCHAR(100) NOT NULL DEFAULT 'main',
    parent_node_id UUID NULL REFERENCES note_section_version_tree(id),
    snapshot_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by UUID NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    label VARCHAR(200) NULL
);

CREATE INDEX IF NOT EXISTS ix_version_tree_project_section
    ON note_section_version_tree(project_id, note_section_id);

CREATE INDEX IF NOT EXISTS ix_version_tree_parent_node
    ON note_section_version_tree(parent_node_id);

COMMIT;
