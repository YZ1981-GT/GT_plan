-- V267: 高级查询运行记录与查询证据
-- Spec: advanced-query-artifact-and-freshness
-- R1.3 / R4.3：身份字段由 PostgreSQL 触发器锁定，运行计数与证据状态保留可变字段。

CREATE TABLE IF NOT EXISTS query_runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    entry             VARCHAR(16) NOT NULL,
    origin            VARCHAR(16) NOT NULL DEFAULT 'direct',
    template_id       UUID NULL,
    project_id        UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    year              INTEGER NULL,
    source_key        VARCHAR(200) NOT NULL,
    definition        JSONB NOT NULL DEFAULT '{}'::jsonb,
    definition_hash   CHAR(64) NOT NULL,
    definition_version SMALLINT NOT NULL DEFAULT 1,
    scope             JSONB NOT NULL DEFAULT '{}'::jsonb,
    labels            JSONB NOT NULL DEFAULT '{}'::jsonb,
    version_vector    JSONB NOT NULL,
    vector_hash       CHAR(64) NOT NULL,
    vector_weak       BOOLEAN NOT NULL DEFAULT FALSE,
    captured_at       TIMESTAMPTZ NOT NULL,
    execution_count   INTEGER NOT NULL DEFAULT 1,
    first_executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_executed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_total        BIGINT NULL,
    last_warnings     JSONB NOT NULL DEFAULT '[]'::jsonb,
    hidden_at         TIMESTAMPTZ NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_query_runs_identity UNIQUE (user_id, entry, definition_hash, vector_hash),
    CONSTRAINT ck_query_runs_entry CHECK (entry IN ('business', 'builder')),
    CONSTRAINT ck_query_runs_origin CHECK (origin IN ('direct', 'template')),
    CONSTRAINT ck_query_runs_hashes CHECK (
        definition_hash ~ '^[0-9a-f]{64}$' AND vector_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_query_runs_count CHECK (execution_count >= 1)
);

CREATE INDEX IF NOT EXISTS ix_query_runs_history
    ON query_runs (user_id, entry, last_executed_at DESC)
    WHERE hidden_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_query_runs_definition
    ON query_runs (user_id, definition_hash, last_executed_at DESC);
CREATE INDEX IF NOT EXISTS ix_query_runs_project ON query_runs (project_id);

CREATE TABLE IF NOT EXISTS query_artifacts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID NULL REFERENCES query_runs(id) ON DELETE SET NULL,
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    entry            VARCHAR(16) NOT NULL,
    project_id       UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    year             INTEGER NULL,
    source_key       VARCHAR(200) NOT NULL,
    definition_hash  CHAR(64) NOT NULL,
    version_vector   JSONB NOT NULL,
    vector_hash      CHAR(64) NOT NULL,
    scope            JSONB NOT NULL DEFAULT '{}'::jsonb,
    status           VARCHAR(16) NOT NULL DEFAULT 'ready',
    file_name        VARCHAR(255) NOT NULL,
    storage_key      TEXT NOT NULL,
    media_type       VARCHAR(120) NOT NULL,
    byte_size        BIGINT NOT NULL,
    sha256           CHAR(64) NOT NULL,
    row_count        BIGINT NOT NULL,
    columns          JSONB NOT NULL,
    manifest         JSONB NOT NULL,
    manifest_sha256  CHAR(64) NOT NULL,
    retention_until  TIMESTAMPTZ NOT NULL,
    purged_at        TIMESTAMPTZ NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_query_artifacts_storage UNIQUE (storage_key),
    CONSTRAINT ck_query_artifacts_entry CHECK (entry IN ('business', 'builder')),
    CONSTRAINT ck_query_artifacts_status CHECK (status IN ('ready', 'purged')),
    CONSTRAINT ck_query_artifacts_purged CHECK (
        (status = 'purged') = (purged_at IS NOT NULL)
    ),
    CONSTRAINT ck_query_artifacts_hashes CHECK (
        sha256 ~ '^[0-9a-f]{64}$' AND manifest_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_query_artifacts_sizes CHECK (byte_size >= 0 AND row_count >= 0)
);

CREATE INDEX IF NOT EXISTS ix_query_artifacts_user
    ON query_artifacts (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_query_artifacts_expiry
    ON query_artifacts (retention_until)
    WHERE status = 'ready';
CREATE INDEX IF NOT EXISTS ix_query_artifacts_run ON query_artifacts (run_id);
CREATE INDEX IF NOT EXISTS ix_query_artifacts_definition
    ON query_artifacts (user_id, definition_hash);

CREATE OR REPLACE FUNCTION gt_query_run_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.user_id IS DISTINCT FROM OLD.user_id
       OR NEW.entry IS DISTINCT FROM OLD.entry
       OR NEW.origin IS DISTINCT FROM OLD.origin
       OR NEW.template_id IS DISTINCT FROM OLD.template_id
       OR NEW.project_id IS DISTINCT FROM OLD.project_id
       OR NEW.year IS DISTINCT FROM OLD.year
       OR NEW.source_key IS DISTINCT FROM OLD.source_key
       OR NEW.definition IS DISTINCT FROM OLD.definition
       OR NEW.definition_hash IS DISTINCT FROM OLD.definition_hash
       OR NEW.definition_version IS DISTINCT FROM OLD.definition_version
       OR NEW.scope IS DISTINCT FROM OLD.scope
       OR NEW.labels IS DISTINCT FROM OLD.labels
       OR NEW.version_vector IS DISTINCT FROM OLD.version_vector
       OR NEW.vector_hash IS DISTINCT FROM OLD.vector_hash
       OR NEW.vector_weak IS DISTINCT FROM OLD.vector_weak
       OR NEW.captured_at IS DISTINCT FROM OLD.captured_at
       OR NEW.first_executed_at IS DISTINCT FROM OLD.first_executed_at
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'query_runs identity fields are immutable (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_query_run_immutable ON query_runs;
CREATE TRIGGER trg_query_run_immutable
    BEFORE UPDATE ON query_runs
    FOR EACH ROW EXECUTE FUNCTION gt_query_run_immutable();

CREATE OR REPLACE FUNCTION gt_query_artifact_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.user_id IS DISTINCT FROM OLD.user_id
       OR NEW.entry IS DISTINCT FROM OLD.entry
       OR NEW.project_id IS DISTINCT FROM OLD.project_id
       OR NEW.year IS DISTINCT FROM OLD.year
       OR NEW.source_key IS DISTINCT FROM OLD.source_key
       OR NEW.definition_hash IS DISTINCT FROM OLD.definition_hash
       OR NEW.version_vector IS DISTINCT FROM OLD.version_vector
       OR NEW.vector_hash IS DISTINCT FROM OLD.vector_hash
       OR NEW.scope IS DISTINCT FROM OLD.scope
       OR NEW.file_name IS DISTINCT FROM OLD.file_name
       OR NEW.storage_key IS DISTINCT FROM OLD.storage_key
       OR NEW.media_type IS DISTINCT FROM OLD.media_type
       OR NEW.byte_size IS DISTINCT FROM OLD.byte_size
       OR NEW.sha256 IS DISTINCT FROM OLD.sha256
       OR NEW.row_count IS DISTINCT FROM OLD.row_count
       OR NEW.columns IS DISTINCT FROM OLD.columns
       OR NEW.manifest IS DISTINCT FROM OLD.manifest
       OR NEW.manifest_sha256 IS DISTINCT FROM OLD.manifest_sha256
       OR NEW.retention_until IS DISTINCT FROM OLD.retention_until
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'query_artifacts identity fields are immutable (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.run_id IS DISTINCT FROM OLD.run_id AND NEW.run_id IS NOT NULL THEN
        RAISE EXCEPTION 'query_artifacts run_id may only be cleared (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status = 'purged' AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'purged query artifact cannot be restored (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status = 'ready' AND NEW.status NOT IN ('ready', 'purged') THEN
        RAISE EXCEPTION 'invalid query artifact status transition (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status = 'ready' AND NEW.purged_at IS NOT NULL THEN
        RAISE EXCEPTION 'ready query artifact cannot have purged_at (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status = 'purged' AND NEW.purged_at IS NULL THEN
        RAISE EXCEPTION 'purged query artifact requires purged_at (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_query_artifact_immutable ON query_artifacts;
CREATE TRIGGER trg_query_artifact_immutable
    BEFORE UPDATE ON query_artifacts
    FOR EACH ROW EXECUTE FUNCTION gt_query_artifact_immutable();
