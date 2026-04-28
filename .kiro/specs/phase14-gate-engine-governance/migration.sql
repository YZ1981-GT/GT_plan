-- Phase 14 migration draft: gate decisions
BEGIN;

CREATE TABLE IF NOT EXISTS gate_decisions (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    wp_id UUID NULL,
    gate_type VARCHAR(32) NOT NULL,
    decision VARCHAR(16) NOT NULL,
    hit_rules JSONB NOT NULL,
    actor_id UUID NOT NULL,
    trace_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gate_decisions_project_gate
ON gate_decisions(project_id, gate_type, created_at DESC);

COMMIT;
