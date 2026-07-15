-- V103: ACNR ProjectOverlay 持久化表
-- Requirements: Req-4 (Overlay 持久化与归属校验)

CREATE TABLE IF NOT EXISTS acnr_project_overlay (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_id UUID REFERENCES working_paper(id),
    parent_wp_code VARCHAR(20) NOT NULL,
    sheet_code VARCHAR(40) NOT NULL,
    overlay_type VARCHAR(20) NOT NULL,  -- 'alias' | 'cust' | 'binding'
    payload JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_overlay_project ON acnr_project_overlay(project_id);

COMMENT ON TABLE acnr_project_overlay IS 'ACNR L2 ProjectOverlay 持久化 — 项目级别名/CUST覆盖/binding';
COMMENT ON COLUMN acnr_project_overlay.overlay_type IS 'alias | cust | binding';
COMMENT ON COLUMN acnr_project_overlay.payload IS '覆盖字段 JSON（如 sheet_name_alias_add 等）';
