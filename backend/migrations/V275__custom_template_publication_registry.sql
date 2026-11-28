-- V272: 自定义底稿模板 publication 登记持久化
-- Spec: custom-workpaper-template-ingestion-and-sync-closure（publication registry）
--
-- 背景：`app/services/custom_template_ingestion/publication_ops.py` 的
-- `PublicationRegistry` 此前是纯内存 dataclass，进程重启即丢失全部
-- publication 与项目 pin；`finalize_saga.begin_pending_visibility` 也只
-- 返回 record 不落库。本迁移补持久化，供 finalize → publication → instantiate
-- 链路在真实 PG 上工作。
--
-- 全部 additive / IF NOT EXISTS；不改变既有表语义。

CREATE TABLE IF NOT EXISTS custom_template_publications (
    id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id    VARCHAR(64)   NOT NULL,
    publication_key    VARCHAR(160)  NOT NULL,
    candidate_id       VARCHAR(160)  NOT NULL,
    candidate_digest   CHAR(64)      NOT NULL,
    authority_ref      VARCHAR(160)  NOT NULL,
    artifact_digest    CHAR(64)      NOT NULL,
    state              VARCHAR(32)   NOT NULL,
    reason             VARCHAR(64),
    handoff            JSONB         NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_custom_publication_org_key UNIQUE (organization_id, publication_key),
    CONSTRAINT ck_custom_publication_state CHECK (
        state IN ('PENDING_VISIBILITY', 'ACTIVE', 'WITHDRAWN', 'SECURITY_REVOKED', 'FAILED')
    ),
    CONSTRAINT ck_custom_publication_candidate_digest CHECK (candidate_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_custom_publication_artifact_digest CHECK (artifact_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_custom_publication_handoff_object CHECK (jsonb_typeof(handoff) = 'object')
);

COMMENT ON TABLE custom_template_publications IS
    '自定义底稿模板 publication 登记：一行一个不可变 publication，新 version 不覆盖旧 artifact。';
COMMENT ON COLUMN custom_template_publications.publication_key IS
    '业务侧 publication 标识（PublicationRegistry 的 key），组织内唯一。';
COMMENT ON COLUMN custom_template_publications.artifact_digest IS
    '冻结的 artifact 内容摘要；写入后不可变，用于自证 publication 绑定的内容。';

CREATE INDEX IF NOT EXISTS ix_custom_publication_org_state
    ON custom_template_publications (organization_id, state);

CREATE TABLE IF NOT EXISTS custom_template_publication_pins (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id VARCHAR(64) NOT NULL,
    project_id     UUID         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    publication_id UUID         NOT NULL REFERENCES custom_template_publications(id) ON DELETE RESTRICT,
    pinned_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_custom_publication_pin_project UNIQUE (project_id)
);

COMMENT ON TABLE custom_template_publication_pins IS
    '项目 pin 的 publication；同一项目同一时刻只有一个生效 pin（唯一约束保证）。';
COMMENT ON CONSTRAINT uq_custom_publication_pin_project ON custom_template_publication_pins IS
    '一个项目只能 pin 一个 publication；升级即改写本行，历史由 publication 表保留。';
