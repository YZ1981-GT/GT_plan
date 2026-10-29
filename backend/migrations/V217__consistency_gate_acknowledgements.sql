-- S2 ADR-CCN-06: 门禁逐项确认留痕
CREATE TABLE IF NOT EXISTS consistency_gate_acknowledgements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    year INT NOT NULL,
    check_name VARCHAR(128) NOT NULL,
    branch_id VARCHAR(64) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL,
    result_fingerprint VARCHAR(128) NOT NULL,
    reason TEXT NOT NULL,
    acknowledged_by UUID NOT NULL,
    acknowledged_role VARCHAR(64) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    revoked_by UUID
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cga_active
    ON consistency_gate_acknowledgements (project_id, year, check_name)
    WHERE revoked_at IS NULL;
