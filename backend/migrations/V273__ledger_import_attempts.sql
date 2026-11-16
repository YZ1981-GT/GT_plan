-- V271: 账套导入 attempt 最小持久化基础（阶段 B）
-- 不写四表金额；合同由应用层按 UnitConfirmationInput 严格校验后写入。

CREATE TABLE IF NOT EXISTS ledger_import_attempts (
    id                         UUID PRIMARY KEY,
    project_id                 UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year                       INTEGER NOT NULL,
    dataset_id                 UUID NULL REFERENCES ledger_datasets(id) ON DELETE SET NULL,
    base_dataset_id            UUID NULL REFERENCES ledger_datasets(id) ON DELETE SET NULL,
    base_unit_contract_digest  VARCHAR(64) NULL,
    upload_token               VARCHAR(64) NOT NULL,
    status                     VARCHAR(32) NOT NULL DEFAULT 'building',
    current_phase              VARCHAR(64) NULL,
    created_by                 UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload_style              VARCHAR(32) NOT NULL,
    unit_confirmation          JSONB NOT NULL,
    unit_contract_digest       VARCHAR(64) NULL,
    bundle_digest              VARCHAR(64) NULL,
    failure_code               VARCHAR(80) NULL,
    CONSTRAINT ck_ledger_import_attempt_status CHECK (
        status IN ('building', 'sealed', 'activating', 'activated',
                   'cleanup_pending', 'cleanup_done')
    ),
    CONSTRAINT ck_ledger_import_attempt_payload_style CHECK (
        payload_style IN ('account_chart', 'ledger')
    ),
    CONSTRAINT ck_ledger_import_attempt_base_digest_length CHECK (
        base_unit_contract_digest IS NULL OR length(base_unit_contract_digest) = 64
    ),
    CONSTRAINT ck_ledger_import_attempt_contract_digest_length CHECK (
        unit_contract_digest IS NULL OR length(unit_contract_digest) = 64
    ),
    CONSTRAINT ck_ledger_import_attempt_bundle_digest_length CHECK (
        bundle_digest IS NULL OR length(bundle_digest) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_ledger_import_attempts_project_year
    ON ledger_import_attempts (project_id, year);
CREATE INDEX IF NOT EXISTS idx_ledger_import_attempts_status
    ON ledger_import_attempts (status);
CREATE INDEX IF NOT EXISTS idx_ledger_import_attempts_upload_token
    ON ledger_import_attempts (upload_token);
