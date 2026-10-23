-- V204: 集团级附注披露模板下推日志表
-- spec: consol-note-template-push-to-subsidiaries

CREATE TABLE IF NOT EXISTS consol_note_template_push_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consol_project_id UUID NOT NULL REFERENCES projects(id),
    section_id TEXT NOT NULL,
    template_version_id UUID NOT NULL,
    pushed_by UUID,
    pushed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    entity_count INT NOT NULL DEFAULT 0,
    success_count INT NOT NULL DEFAULT 0,
    failure_count INT NOT NULL DEFAULT 0,
    failures JSONB DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_consol_note_push_log_project
    ON consol_note_template_push_log(consol_project_id, section_id);
