-- V249: 附注公式执行可查询运行记录（S5 / ADR-FPE-08、13、14）。
CREATE TABLE IF NOT EXISTS note_formula_run (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    note_section VARCHAR(100) NOT NULL,
    trigger VARCHAR(40) NOT NULL DEFAULT 'manual',
    triggered_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    executed_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT NULL,
    CONSTRAINT ck_note_formula_run_status
        CHECK (status IN ('running', 'succeeded', 'partial', 'failed'))
);
CREATE INDEX IF NOT EXISTS idx_note_formula_run_project_year_section
    ON note_formula_run (project_id, year, note_section, started_at DESC);
