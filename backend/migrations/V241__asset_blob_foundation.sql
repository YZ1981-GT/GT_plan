-- 附件平台跨模块闭环：不可变字节对象、知识晋升与 AI run 资源（additive）。
CREATE TABLE IF NOT EXISTS asset_blobs (
    id UUID PRIMARY KEY,
    content_hash VARCHAR(64) NOT NULL,
    byte_size BIGINT NOT NULL,
    detected_media_type VARCHAR(128),
    storage_type VARCHAR(24) NOT NULL,
    storage_key TEXT NOT NULL,
    ingress_policy_version VARCHAR(32) NOT NULL DEFAULT 'apc-v1',
    security_status VARCHAR(20) NOT NULL DEFAULT 'accepted',
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_asset_blobs_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_asset_blobs_size CHECK (byte_size >= 0),
    CONSTRAINT ck_asset_blobs_security CHECK (security_status IN ('accepted','quarantined','rejected')),
    CONSTRAINT ck_asset_blobs_actor CHECK (
        (actor_type = 'user' AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR (actor_type = 'service' AND actor_user_id IS NULL AND actor_service_identity_id IS NOT NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_asset_blobs_storage
    ON asset_blobs (storage_type, storage_key);
CREATE INDEX IF NOT EXISTS ix_asset_blobs_hash_size
    ON asset_blobs (content_hash, byte_size);

ALTER TABLE attachment_versions ADD COLUMN IF NOT EXISTS blob_id UUID;
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS blob_id UUID;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_attachment_versions_blob') THEN
        ALTER TABLE attachment_versions ADD CONSTRAINT fk_attachment_versions_blob
            FOREIGN KEY (blob_id) REFERENCES asset_blobs(id) ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_knowledge_documents_blob') THEN
        ALTER TABLE knowledge_documents ADD CONSTRAINT fk_knowledge_documents_blob
            FOREIGN KEY (blob_id) REFERENCES asset_blobs(id) ON DELETE RESTRICT;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_attachment_versions_blob ON attachment_versions(blob_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_blob ON knowledge_documents(blob_id);

-- staged finalize 可把 blob_id 从 NULL 补为确定值一次；一旦存在即与 hash/key 一样不可改、不可清空。
CREATE OR REPLACE FUNCTION evgov_attachment_version_immutable() RETURNS trigger AS $fn$
BEGIN
    IF NEW.byte_size IS DISTINCT FROM OLD.byte_size
       OR NEW.storage_key IS DISTINCT FROM OLD.storage_key
       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
       OR (OLD.blob_id IS NOT NULL AND NEW.blob_id IS DISTINCT FROM OLD.blob_id)
       OR NEW.attachment_id IS DISTINCT FROM OLD.attachment_id
       OR NEW.version_no IS DISTINCT FROM OLD.version_no
       OR NEW.actor_type IS DISTINCT FROM OLD.actor_type
       OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
       OR NEW.actor_service_identity_id IS DISTINCT FROM OLD.actor_service_identity_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'attachment_versions immutable identity cannot be updated (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS knowledge_evidence_promotions (
    id UUID PRIMARY KEY,
    source_document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE RESTRICT,
    source_document_version INTEGER NOT NULL,
    source_blob_id UUID NOT NULL REFERENCES asset_blobs(id) ON DELETE RESTRICT,
    source_hash VARCHAR(64) NOT NULL,
    target_attachment_id UUID NOT NULL REFERENCES attachments(id) ON DELETE RESTRICT,
    target_attachment_version_id UUID NOT NULL REFERENCES attachment_versions(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    actor_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_kep_hash CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT uq_kep_idempotency UNIQUE (project_id, actor_user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_kep_source ON knowledge_evidence_promotions(source_document_id, source_document_version);
CREATE INDEX IF NOT EXISTS ix_kep_target ON knowledge_evidence_promotions(target_attachment_id);

CREATE OR REPLACE FUNCTION gt_knowledge_evidence_promotion_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'knowledge evidence promotion is append-only';
END $$;
DROP TRIGGER IF EXISTS trg_knowledge_evidence_promotion_append_only ON knowledge_evidence_promotions;
CREATE TRIGGER trg_knowledge_evidence_promotion_append_only
BEFORE UPDATE OR DELETE ON knowledge_evidence_promotions
FOR EACH ROW EXECUTE FUNCTION gt_knowledge_evidence_promotion_append_only();

CREATE TABLE IF NOT EXISTS ai_chat_run_resources (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES ai_chat_runs(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES ai_chat_session(id) ON DELETE CASCADE,
    resource_kind VARCHAR(32) NOT NULL,
    resource_id UUID NOT NULL,
    attachment_version_id UUID REFERENCES attachment_versions(id) ON DELETE RESTRICT,
    blob_id UUID REFERENCES asset_blobs(id) ON DELETE RESTRICT,
    content_hash VARCHAR(64),
    actor_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ai_run_resource_kind CHECK (resource_kind IN ('chat_upload','project_attachment')),
    CONSTRAINT ck_ai_run_project_attachment_pin CHECK (
        resource_kind <> 'project_attachment'
        OR (
            attachment_version_id IS NOT NULL
            AND blob_id IS NOT NULL
            AND content_hash ~ '^[0-9a-f]{64}$'
        )
    ),
    CONSTRAINT uq_ai_run_resource UNIQUE (run_id, resource_kind, resource_id)
);
CREATE INDEX IF NOT EXISTS ix_ai_run_resources_session ON ai_chat_run_resources(session_id, run_id);

CREATE OR REPLACE FUNCTION gt_ai_run_resource_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'AI run resource pin is immutable';
END $$;
DROP TRIGGER IF EXISTS trg_ai_run_resource_immutable ON ai_chat_run_resources;
CREATE TRIGGER trg_ai_run_resource_immutable BEFORE UPDATE ON ai_chat_run_resources
FOR EACH ROW EXECUTE FUNCTION gt_ai_run_resource_immutable();

CREATE OR REPLACE FUNCTION gt_asset_blob_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.content_hash IS DISTINCT FROM OLD.content_hash
       OR NEW.byte_size IS DISTINCT FROM OLD.byte_size
       OR NEW.detected_media_type IS DISTINCT FROM OLD.detected_media_type
       OR NEW.storage_type IS DISTINCT FROM OLD.storage_type
       OR NEW.storage_key IS DISTINCT FROM OLD.storage_key
       OR NEW.ingress_policy_version IS DISTINCT FROM OLD.ingress_policy_version
       OR NEW.actor_type IS DISTINCT FROM OLD.actor_type
       OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
       OR NEW.actor_service_identity_id IS DISTINCT FROM OLD.actor_service_identity_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'asset blob identity is immutable';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_asset_blob_immutable ON asset_blobs;
CREATE TRIGGER trg_asset_blob_immutable BEFORE UPDATE ON asset_blobs
FOR EACH ROW EXECUTE FUNCTION gt_asset_blob_immutable();
