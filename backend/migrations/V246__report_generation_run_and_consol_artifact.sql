-- V242：共享报表运行 + 合并不可变 artifact（consolidation-run-and-workpaper-lifecycle-closure 批 4）
--
-- report_generation_run 采用 formula-provenance-envelope 约定的共享名称；rows_json 保存本次规范行快照。
-- financial_report 继续作为全平台“当前槽位”，只增加 run_id/provenance，不叠加历史重复行。
-- consol_artifact 绑定成功 report run；ready 后由服务层禁止覆盖，下载前重验 size + SHA-256。

CREATE TABLE IF NOT EXISTS report_generation_run (
    id                  UUID        PRIMARY KEY,
    project_id          UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year                INTEGER     NOT NULL,
    trigger             VARCHAR(40) NOT NULL,
    triggered_by        UUID        REFERENCES users(id) ON DELETE SET NULL,
    operation_id        UUID        REFERENCES consol_operation(id) ON DELETE SET NULL,
    operation_revision  INTEGER,
    node_key            VARCHAR(160),
    applicable_standard VARCHAR(80),
    status              VARCHAR(20) NOT NULL DEFAULT 'building',
    calc_version        INTEGER     NOT NULL,
    changed_rows        INTEGER     NOT NULL DEFAULT 0,
    recomputed_rows     INTEGER     NOT NULL DEFAULT 0,
    failed_rows         INTEGER     NOT NULL DEFAULT 0,
    row_count           INTEGER     NOT NULL DEFAULT 0,
    report_types        JSONB       NOT NULL DEFAULT '[]'::jsonb,
    input_digest        CHAR(64),
    row_digest          CHAR(64),
    rows_json           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    provenance          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    error               TEXT,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_report_generation_run_status CHECK (
        status IN ('building', 'succeeded', 'failed', 'stale')
    ),
    CONSTRAINT ck_report_generation_run_revision CHECK (
        operation_revision IS NULL OR operation_revision > 0
    ),
    CONSTRAINT ck_report_generation_run_counts CHECK (
        changed_rows >= 0 AND recomputed_rows >= 0 AND failed_rows >= 0 AND row_count >= 0
    ),
    CONSTRAINT ck_report_generation_run_input_digest CHECK (
        input_digest IS NULL OR length(input_digest) = 64
    ),
    CONSTRAINT ck_report_generation_run_row_digest CHECK (
        row_digest IS NULL OR length(row_digest) = 64
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_report_generation_run_operation_revision
    ON report_generation_run (operation_id, operation_revision, project_id, node_key)
    WHERE operation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_report_generation_run_project_year
    ON report_generation_run (project_id, year, status, finished_at DESC);

ALTER TABLE financial_report
    ADD COLUMN IF NOT EXISTS run_id UUID REFERENCES report_generation_run(id) ON DELETE SET NULL;
ALTER TABLE financial_report
    ADD COLUMN IF NOT EXISTS provenance JSONB;
CREATE INDEX IF NOT EXISTS ix_financial_report_run_id ON financial_report (run_id);

CREATE TABLE IF NOT EXISTS consol_artifact (
    id                  UUID         PRIMARY KEY,
    project_id          UUID         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year                INTEGER      NOT NULL,
    operation_id        UUID         REFERENCES consol_operation(id) ON DELETE SET NULL,
    operation_revision  INTEGER,
    report_run_id       UUID         NOT NULL REFERENCES report_generation_run(id) ON DELETE RESTRICT,
    node_key            VARCHAR(160) NOT NULL,
    kind                VARCHAR(32)  NOT NULL,
    status              VARCHAR(20)  NOT NULL DEFAULT 'generating',
    file_name           VARCHAR(255) NOT NULL,
    storage_path        TEXT,
    content_type        VARCHAR(120) NOT NULL,
    size_bytes          BIGINT,
    sha256              CHAR(64),
    manifest_json       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    error               TEXT,
    created_by          UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ready_at            TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT ck_consol_artifact_kind CHECK (
        kind IN ('report_excel', 'consol_workpaper')
    ),
    CONSTRAINT ck_consol_artifact_status CHECK (
        status IN ('generating', 'ready', 'failed')
    ),
    CONSTRAINT ck_consol_artifact_revision CHECK (
        operation_revision IS NULL OR operation_revision > 0
    ),
    CONSTRAINT ck_consol_artifact_size CHECK (size_bytes IS NULL OR size_bytes >= 0),
    CONSTRAINT ck_consol_artifact_sha256 CHECK (sha256 IS NULL OR length(sha256) = 64),
    CONSTRAINT ck_consol_artifact_ready_fields CHECK (
        status <> 'ready' OR (
            storage_path IS NOT NULL AND size_bytes IS NOT NULL
            AND sha256 IS NOT NULL AND ready_at IS NOT NULL
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_consol_artifact_report_kind_node
    ON consol_artifact (report_run_id, kind, node_key);
CREATE INDEX IF NOT EXISTS ix_consol_artifact_project_year
    ON consol_artifact (project_id, year, created_at DESC);

COMMENT ON TABLE report_generation_run IS
    '共享报表生成运行；rows_json/row_digest 是该次运行的不可变规范行快照';
COMMENT ON COLUMN financial_report.run_id IS
    '生成当前报表行值的 report_generation_run；历史精确行集读取 run.rows_json';
COMMENT ON TABLE consol_artifact IS
    '绑定成功合并报表运行的一次生成、重复下载不重算的不可变 Excel artifact';
