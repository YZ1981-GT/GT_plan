-- V216：底稿两阶段生成 operation 与 item
--
-- operation 以客户端 UUID 为幂等身份；Phase A 只保存描述符和预留 UUID，
-- 文件在项目锁外写 staging，Phase B 复核后才建立正式底稿行并提升文件。
-- 状态单调迁移由服务层 CAS 保证；本迁移用 CHECK 封闭合法值。

CREATE TABLE IF NOT EXISTS workpaper_generation_operations (
    id                  UUID         PRIMARY KEY,
    project_id          UUID         NOT NULL
        REFERENCES projects(id) ON DELETE CASCADE,
    year                INTEGER      NOT NULL,
    actor_user_id       UUID         NOT NULL
        REFERENCES users(id) ON DELETE RESTRICT,
    kind                VARCHAR(32)  NOT NULL,
    template_set_id     UUID
        REFERENCES wp_template_set(id) ON DELETE SET NULL,
    failure_policy      VARCHAR(16)  NOT NULL,
    request_payload     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    request_hash        CHAR(64)     NOT NULL,
    scope_revision      CHAR(64)     NOT NULL,
    status              VARCHAR(32)  NOT NULL DEFAULT 'prepared',
    lease_token         UUID,
    lease_expires_at    TIMESTAMPTZ,
    attempt             INTEGER      NOT NULL DEFAULT 0,
    progress_total      INTEGER      NOT NULL DEFAULT 0,
    progress_done       INTEGER      NOT NULL DEFAULT 0,
    receipt             JSONB,
    public_error        TEXT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,

    CONSTRAINT ck_wp_generation_operations_kind CHECK (
        kind IN ('template_set', 'from_codes')
    ),
    CONSTRAINT ck_wp_generation_operations_failure_policy CHECK (
        failure_policy IN ('atomic', 'per_item')
    ),
    CONSTRAINT ck_wp_generation_operations_status CHECK (
        status IN (
            'prepared', 'materializing', 'materialized', 'finalizing',
            'succeeded', 'partial_failed', 'failed', 'stale'
        )
    ),
    CONSTRAINT ck_wp_generation_operations_kind_policy CHECK (
        (kind = 'template_set' AND failure_policy = 'atomic') OR
        (kind = 'from_codes' AND failure_policy = 'per_item')
    ),
    CONSTRAINT ck_wp_generation_operations_progress CHECK (
        attempt >= 0 AND progress_total >= 0 AND progress_done >= 0
        AND progress_done <= progress_total
    ),
    CONSTRAINT ck_wp_generation_operations_lease_pair CHECK (
        (lease_token IS NULL AND lease_expires_at IS NULL) OR
        (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
    )
);

-- 项目内状态查询，以及过期 lease 的恢复扫描。
CREATE INDEX IF NOT EXISTS ix_wp_generation_operations_project_status
    ON workpaper_generation_operations (project_id, status, created_at);

CREATE INDEX IF NOT EXISTS ix_wp_generation_operations_lease
    ON workpaper_generation_operations (status, lease_expires_at)
    WHERE status IN (
        'prepared', 'materializing', 'materialized', 'finalizing'
    );

CREATE TABLE IF NOT EXISTS workpaper_generation_items (
    id                    UUID         PRIMARY KEY,
    operation_id          UUID         NOT NULL
        REFERENCES workpaper_generation_operations(id) ON DELETE CASCADE,
    ordinal               INTEGER      NOT NULL,
    wp_code               VARCHAR(80)  NOT NULL,
    wp_name               TEXT         NOT NULL,
    audit_cycle           VARCHAR(40),
    wp_index_id           UUID         NOT NULL,
    wp_id                 UUID         NOT NULL,
    template_source       JSONB,
    template_fingerprint  CHAR(64),
    staging_path          TEXT,
    final_path            TEXT,
    file_sha256           CHAR(64),
    from_template         BOOLEAN      NOT NULL DEFAULT false,
    header_prepared       BOOLEAN      NOT NULL DEFAULT false,
    header_issue          TEXT,
    status                VARCHAR(32)  NOT NULL DEFAULT 'prepared',
    error                 TEXT,

    CONSTRAINT ck_wp_generation_items_status CHECK (
        status IN (
            'prepared', 'materializing', 'materialized', 'finalizing',
            'succeeded', 'partial_failed', 'failed', 'stale'
        )
    ),
    CONSTRAINT ck_wp_generation_items_ordinal CHECK (ordinal >= 0)
);

-- 两组唯一键同时保证同一 operation 内编码和顺序稳定。
CREATE UNIQUE INDEX IF NOT EXISTS uq_wp_generation_items_operation_code
    ON workpaper_generation_items (operation_id, wp_code);

CREATE UNIQUE INDEX IF NOT EXISTS uq_wp_generation_items_operation_ordinal
    ON workpaper_generation_items (operation_id, ordinal);

CREATE INDEX IF NOT EXISTS ix_wp_generation_items_operation_status
    ON workpaper_generation_items (operation_id, status, ordinal);

COMMENT ON TABLE workpaper_generation_operations IS
    '可恢复的底稿两阶段生成操作；id 是客户端幂等身份，terminal receipt 永久复用';
COMMENT ON TABLE workpaper_generation_items IS
    '底稿生成明细；保存预留正式身份、模板来源摘要和 staging/final manifest';
COMMENT ON COLUMN workpaper_generation_items.wp_index_id IS
    'Phase A 预留的 wp_index UUID；正式行在 Phase B 才创建，故本列不提前建目标表外键';
COMMENT ON COLUMN workpaper_generation_items.wp_id IS
    'Phase A 预留的 working_paper UUID；正式行在 Phase B 才创建，故本列不提前建目标表外键';
