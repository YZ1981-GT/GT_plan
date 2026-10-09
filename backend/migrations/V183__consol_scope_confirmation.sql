-- D5: 用户明确确认后的合并范围版本与角色稳定键快照。
-- 只保存节点身份，不复制 projects、试算表、分录或金额。

CREATE TABLE IF NOT EXISTS consol_scope_confirmations (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    report_scope VARCHAR(20) NOT NULL,
    revision INTEGER NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    canonical_payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    confirmed_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_consol_scope_confirmation_revision CHECK (revision > 0),
    CONSTRAINT ck_consol_scope_confirmation_fingerprint CHECK (length(fingerprint) = 64),
    CONSTRAINT ck_consol_scope_confirmation_status CHECK (status IN ('active', 'superseded')),
    CONSTRAINT uq_consol_scope_confirmation_revision
        UNIQUE (project_id, year, report_scope, revision)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_consol_scope_confirmation_active
    ON consol_scope_confirmations (project_id, year, report_scope)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_consol_scope_confirmation_fingerprint
    ON consol_scope_confirmations (project_id, fingerprint);

CREATE TABLE IF NOT EXISTS consol_scope_confirmation_nodes (
    id UUID PRIMARY KEY,
    confirmation_id UUID NOT NULL REFERENCES consol_scope_confirmations(id) ON DELETE CASCADE,
    node_key VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    company_code VARCHAR(100) NOT NULL,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    host_project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    parent_node_key VARCHAR(255),
    position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_consol_scope_confirmation_node_key UNIQUE (confirmation_id, node_key),
    CONSTRAINT uq_consol_scope_confirmation_node_position UNIQUE (confirmation_id, position),
    CONSTRAINT ck_consol_scope_confirmation_node_position CHECK (position >= 0)
);
CREATE INDEX IF NOT EXISTS idx_consol_scope_confirmation_nodes_project
    ON consol_scope_confirmation_nodes (project_id);
