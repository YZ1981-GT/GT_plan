-- V240：持久合并运行根记录（consolidation-run-and-workpaper-lifecycle-closure 批 2）
--
-- running 行是当前执行，queued 行是至多一个已合并的 pending revision。
-- worker 用 revision + lease_owner 双重 CAS；HTTP 请求只入队，不在请求连接内执行合并计算。

CREATE TABLE IF NOT EXISTS consol_operation (
    id                  UUID         PRIMARY KEY,
    project_id          UUID         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year                INTEGER      NOT NULL,
    operation_type      VARCHAR(24)  NOT NULL,
    idempotency_key     VARCHAR(128) NOT NULL,
    idempotency_keys    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    request_hash        CHAR(64)     NOT NULL,
    request_payload     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    context_json        JSONB        NOT NULL DEFAULT '{}'::jsonb,
    version_vector      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    status              VARCHAR(20)  NOT NULL DEFAULT 'queued',
    revision            INTEGER      NOT NULL DEFAULT 1,
    lease_owner         UUID,
    lease_expires_at    TIMESTAMPTZ,
    heartbeat_at        TIMESTAMPTZ,
    attempt             INTEGER      NOT NULL DEFAULT 0,
    steps               JSONB        NOT NULL DEFAULT '[]'::jsonb,
    errors              JSONB        NOT NULL DEFAULT '[]'::jsonb,
    result_refs         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    metrics             JSONB        NOT NULL DEFAULT '{}'::jsonb,
    trigger_source      VARCHAR(40)  NOT NULL,
    triggered_by        UUID REFERENCES users(id) ON DELETE SET NULL,
    queued_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    superseded_by       UUID REFERENCES consol_operation(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT ck_consol_operation_type CHECK (
        operation_type IN ('refresh_all', 'push')
    ),
    CONSTRAINT ck_consol_operation_status CHECK (
        status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'stale', 'cancelled')
    ),
    CONSTRAINT ck_consol_operation_revision CHECK (revision > 0 AND attempt >= 0),
    CONSTRAINT ck_consol_operation_hash CHECK (length(request_hash) = 64),
    CONSTRAINT ck_consol_operation_lease CHECK (
        (status = 'running' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (status <> 'running' AND lease_owner IS NULL AND lease_expires_at IS NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_consol_operation_idempotency
    ON consol_operation (project_id, year, idempotency_key);

CREATE UNIQUE INDEX IF NOT EXISTS ux_consol_operation_running
    ON consol_operation (project_id, year)
    WHERE status = 'running';

CREATE UNIQUE INDEX IF NOT EXISTS ux_consol_operation_queued
    ON consol_operation (project_id, year)
    WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS ix_consol_operation_project_year
    ON consol_operation (project_id, year, queued_at DESC);

CREATE INDEX IF NOT EXISTS ix_consol_operation_claim
    ON consol_operation (status, lease_expires_at, queued_at);

ALTER TABLE consol_push_run
    ADD COLUMN IF NOT EXISTS operation_id UUID REFERENCES consol_operation(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_consol_push_run_operation
    ON consol_push_run (operation_id)
    WHERE operation_id IS NOT NULL;

COMMENT ON TABLE consol_operation IS
    '持久合并运行根；每项目年度至多一个 running 和一个已合并 queued revision';
COMMENT ON COLUMN consol_operation.idempotency_keys IS
    '本行吸收过的 idempotency key 到原始 canonical request hash 的映射';
COMMENT ON COLUMN consol_operation.revision IS
    'queued 请求被新触发合并时递增；所有 worker 写回必须同时校验 revision 与 lease_owner';
