-- V220：批量建项上传一次、预校验后按持久计划执行

CREATE TABLE IF NOT EXISTS project_batch_import_plans (
    id                UUID        PRIMARY KEY,
    actor_user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    mode              VARCHAR(24) NOT NULL,
    status            VARCHAR(24) NOT NULL DEFAULT 'validated',
    file_name         TEXT        NOT NULL,
    file_sha256       CHAR(64)    NOT NULL,
    template_version  VARCHAR(16),
    request_hash      CHAR(64)    NOT NULL,
    idempotency_key   VARCHAR(64) NOT NULL,
    rows              JSONB       NOT NULL DEFAULT '[]'::jsonb,
    tree_preview      JSONB       NOT NULL DEFAULT '[]'::jsonb,
    summary           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    warnings          JSONB       NOT NULL DEFAULT '[]'::jsonb,
    receipt           JSONB,
    public_error      TEXT,
    expires_at        TIMESTAMPTZ NOT NULL,
    applied_at        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_project_batch_plans_mode
        CHECK (mode IN ('project', 'consolidation')),
    CONSTRAINT ck_project_batch_plans_status
        CHECK (status IN ('invalid', 'validated', 'applying', 'applied', 'failed', 'expired'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_batch_plans_actor_key
    ON project_batch_import_plans (actor_user_id, idempotency_key);
CREATE INDEX IF NOT EXISTS ix_project_batch_plans_actor_status
    ON project_batch_import_plans (actor_user_id, status, created_at);
CREATE INDEX IF NOT EXISTS ix_project_batch_plans_expiry
    ON project_batch_import_plans (status, expires_at);

COMMENT ON TABLE project_batch_import_plans IS
    '批量建项预校验计划；规范行、最终树预览和 terminal 回执的持久真源';
COMMENT ON COLUMN project_batch_import_plans.request_hash IS
    'mode + 规范行的 UTF-8 canonical JSON SHA-256；同幂等键不同摘要拒绝';
COMMENT ON COLUMN project_batch_import_plans.rows IS
    '规范行及 Excel 行号、动作、目标项目、集团关系基线摘要';
