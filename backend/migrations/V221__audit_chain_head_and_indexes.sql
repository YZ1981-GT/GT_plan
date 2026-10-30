-- V221: 审计链尾表 + prev_hash/chain 索引
-- spec: audit-log-chain-integrity, ADR-ALC-02 / ADR-ALC-01

CREATE TABLE IF NOT EXISTS audit_chain_head (
    chain_key   VARCHAR(80)   PRIMARY KEY,
    tail_entry_id UUID        NOT NULL,
    tail_hash   VARCHAR(64)   NOT NULL,
    entry_count BIGINT        NOT NULL,
    updated_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_entries_prev_hash
    ON audit_log_entries (prev_hash);

CREATE INDEX IF NOT EXISTS idx_audit_log_entries_chain
    ON audit_log_entries ((payload->>'project_id'));
