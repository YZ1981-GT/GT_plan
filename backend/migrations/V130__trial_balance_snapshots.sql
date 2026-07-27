CREATE TABLE IF NOT EXISTS trial_balance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    year INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    trigger VARCHAR(30) NOT NULL,
    actor_id UUID NULL,
    content_hash VARCHAR(64) NOT NULL,
    snapshot_data JSONB NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    audited_total NUMERIC NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_tb_snapshot_version UNIQUE(project_id, year, version_no)
);
CREATE INDEX IF NOT EXISTS idx_tb_snapshots_project_year_time ON trial_balance_snapshots(project_id, year, created_at DESC);
