-- V107: Evidence Governance — legacy_attachment_alias / 持久 EvidenceRef / EvidenceDependency
--       活动 intent partial unique + canonical edge hash 去重 + 双向查询索引
-- Spec: attachment-ocr-ai-evidence-governance-hardening / Task 2.3 (Wave 1)
-- Requirements: R3（持久 EvidenceRef 与引用完整性）, R4（跨模块关联与项目隔离）,
--               R9（stale 传播与下游阻断 —— 统一依赖图边）, R14（迁移兼容 / legacy ID 解析）
-- Design: §4.1（Attachment 聚合与旧 ID 解析 —— legacy_attachment_alias），
--         §4.4（EvidenceRef 与统一依赖图 —— 持久 EvidenceRef + EvidenceDependency）
-- Properties: P1（项目隔离）, P6（EvidenceRef 完整性）, P7（活动 intent/边幂等）,
--             P8（双向一致）, P20（统一图 canonical edge hash 去重）, P28（迁移幂等）
--
-- 约定（migration_allocation.lint_migration_sql 守卫，design §8.1）：
--   * additive-only：不含 DROP TABLE / DROP COLUMN / TRUNCATE（不删除 legacy 列/结构）。
--   * 可重复检测（幂等）：CREATE TABLE / CREATE (UNIQUE) INDEX 用 IF NOT EXISTS；
--     ADD CONSTRAINT 用 pg_constraint 存在性 DO 守卫。重跑不报错、不重复对象（P28）。
--   * 所有 FK 默认 ON DELETE RESTRICT（回滚不级联删除治理对象；design §8.1 / release-gate）。
--
-- 单一真源（契约）：app.services.evidence_governance.contracts
--   （EVIDENCE_REF_PERSISTENT_COLUMNS / EVIDENCE_REF_ACTIVE_INTENT_UNIQUE /
--    EVIDENCE_REF_STATUSES / LEGACY_ALIAS_COLUMNS / LegacyResolutionKind）；
--   canonical intent_hash / edge_hash 语义见 frozen_contracts.content_hash_of（Task 1.5）。
-- 前置：V106 应已建 attachments 复合 scope key 与 attachment_versions。
-- Repair：部分环境将残缺 V106 记入 schema_version（checksum 与现行文件不一致），
--   attachments.audit_year / attachment_versions 未落库。以下 §R0 幂等补齐后再建 V107 对象。

-- ============================================================
-- R0. 幂等补齐残缺 V106（attachments 治理列 + attachment_versions + 循环 FK/触发器）
-- ============================================================

ALTER TABLE attachments ADD COLUMN IF NOT EXISTS audit_year INTEGER;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS original_file_name VARCHAR(500);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS source_type VARCHAR(50);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS obtained_at TIMESTAMPTZ;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS provider VARCHAR(200);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS is_key_evidence BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS metadata_status VARCHAR(20) NOT NULL DEFAULT 'incomplete';
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS metadata_missing JSONB;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS state VARCHAR(20) NOT NULL DEFAULT 'available';
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS current_version_id UUID;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS actor_type VARCHAR(20);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS actor_user_id UUID;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS actor_service_identity_id UUID;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS original_creator_unknown BOOLEAN NOT NULL DEFAULT false;

UPDATE attachments a
SET audit_year = COALESCE(
    p.audit_year,
    EXTRACT(YEAR FROM p.audit_period_end)::int,
    EXTRACT(YEAR FROM p.audit_period_start)::int
)
FROM projects p
WHERE a.project_id = p.id
  AND a.audit_year IS NULL;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_attachments_state') THEN
        ALTER TABLE attachments ADD CONSTRAINT chk_attachments_state
            CHECK (state IN ('pending','available','inactive','tombstoned'));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_attachments_actor_xor') THEN
        ALTER TABLE attachments ADD CONSTRAINT chk_attachments_actor_xor CHECK (
            actor_type IS NULL
            OR (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
            OR (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
        );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_attachments_actor_user') THEN
        ALTER TABLE attachments ADD CONSTRAINT fk_attachments_actor_user
            FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE RESTRICT;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_attachments_actor_service') THEN
        ALTER TABLE attachments ADD CONSTRAINT fk_attachments_actor_service
            FOREIGN KEY (actor_service_identity_id) REFERENCES service_identities(id) ON DELETE RESTRICT;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_attachments_scope') THEN
        ALTER TABLE attachments ADD CONSTRAINT uq_attachments_scope
            UNIQUE (id, project_id, audit_year);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS attachment_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attachment_id UUID NOT NULL,
    project_id UUID NOT NULL,
    audit_year INTEGER,
    version_no INTEGER NOT NULL,
    storage_type VARCHAR(20) NOT NULL DEFAULT 'paperless',
    storage_key VARCHAR(500),
    media_type VARCHAR(100),
    byte_size BIGINT,
    content_hash VARCHAR(64),
    config_snapshot JSONB,
    availability VARCHAR(20) NOT NULL DEFAULT 'staged',
    previous_version_id UUID,
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    original_creator_unknown BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_av_availability
        CHECK (availability IN ('staged','available','quarantined','inactive')),
    CONSTRAINT chk_av_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_av_scope_identity') THEN
        ALTER TABLE attachment_versions ADD CONSTRAINT uq_av_scope_identity
            UNIQUE (id, attachment_id, project_id, audit_year);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_av_attachment_version') THEN
        ALTER TABLE attachment_versions ADD CONSTRAINT uq_av_attachment_version
            UNIQUE (attachment_id, version_no);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_av_content_hash ON attachment_versions(attachment_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_av_scope ON attachment_versions(project_id, audit_year);
CREATE INDEX IF NOT EXISTS idx_av_availability ON attachment_versions(attachment_id, availability);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_av_parent_scope') THEN
        ALTER TABLE attachment_versions ADD CONSTRAINT fk_av_parent_scope
            FOREIGN KEY (attachment_id, project_id, audit_year)
            REFERENCES attachments(id, project_id, audit_year) ON DELETE RESTRICT;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_av_previous_scope') THEN
        ALTER TABLE attachment_versions ADD CONSTRAINT fk_av_previous_scope
            FOREIGN KEY (previous_version_id, attachment_id, project_id, audit_year)
            REFERENCES attachment_versions(id, attachment_id, project_id, audit_year) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_attachments_current_version') THEN
        ALTER TABLE attachments ADD CONSTRAINT fk_attachments_current_version
            FOREIGN KEY (current_version_id, id, project_id, audit_year)
            REFERENCES attachment_versions(id, attachment_id, project_id, audit_year) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE OR REPLACE FUNCTION evgov_check_av_previous() RETURNS trigger AS $fn$
BEGIN
    IF NEW.previous_version_id IS NOT NULL THEN
        IF NEW.previous_version_id = NEW.id THEN
            RAISE EXCEPTION 'attachment_versions.previous_version_id 不得自指 (id=%)', NEW.id
                USING ERRCODE = 'check_violation';
        END IF;
        PERFORM 1 FROM attachment_versions pv
            WHERE pv.id = NEW.previous_version_id
              AND pv.attachment_id = NEW.attachment_id
              AND pv.project_id = NEW.project_id
              AND pv.audit_year IS NOT DISTINCT FROM NEW.audit_year;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'previous_version_id % 与版本 % 不属于同一聚合根/scope', NEW.previous_version_id, NEW.id
                USING ERRCODE = 'foreign_key_violation';
        END IF;
    END IF;
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION evgov_check_attachment_current() RETURNS trigger AS $fn$
DECLARE
    v_avail text;
BEGIN
    IF NEW.current_version_id IS NOT NULL THEN
        SELECT av.availability INTO v_avail FROM attachment_versions av
            WHERE av.id = NEW.current_version_id
              AND av.attachment_id = NEW.id
              AND av.project_id = NEW.project_id
              AND av.audit_year IS NOT DISTINCT FROM NEW.audit_year;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'current_version_id % 与附件 % 不属于同一聚合根/scope', NEW.current_version_id, NEW.id
                USING ERRCODE = 'foreign_key_violation';
        END IF;
        IF v_avail <> 'available' THEN
            RAISE EXCEPTION 'current_version_id % 不是 available（availability=%）', NEW.current_version_id, v_avail
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_av_previous_link') THEN
        CREATE CONSTRAINT TRIGGER trg_av_previous_link
            AFTER INSERT OR UPDATE ON attachment_versions
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION evgov_check_av_previous();
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_attachment_current_link') THEN
        CREATE CONSTRAINT TRIGGER trg_attachment_current_link
            AFTER INSERT OR UPDATE ON attachments
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION evgov_check_attachment_current();
    END IF;
END $$;

CREATE OR REPLACE FUNCTION evgov_attachment_version_immutable() RETURNS trigger AS $fn$
BEGIN
    IF NEW.byte_size    IS DISTINCT FROM OLD.byte_size
       OR NEW.storage_key  IS DISTINCT FROM OLD.storage_key
       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
       OR NEW.attachment_id IS DISTINCT FROM OLD.attachment_id
       OR NEW.version_no    IS DISTINCT FROM OLD.version_no
       OR NEW.actor_type    IS DISTINCT FROM OLD.actor_type
       OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
       OR NEW.actor_service_identity_id IS DISTINCT FROM OLD.actor_service_identity_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'attachment_versions 不可变列禁止 UPDATE (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_av_immutable
    BEFORE UPDATE ON attachment_versions
    FOR EACH ROW EXECUTE FUNCTION evgov_attachment_version_immutable();

-- ============================================================
-- 0. legacy_attachment_alias —— 旧附件 ID → (新聚合根, 确定版本) 解析（design §4.1）
--    old_attachment_id 不假设等于新聚合根；每个旧行经别名解析到 root + definite version。
--    复合 scope FK，ON DELETE RESTRICT。
-- ============================================================

CREATE TABLE IF NOT EXISTS legacy_attachment_alias (
    old_attachment_id UUID PRIMARY KEY,                    -- 旧 attachments.id（不假设 == 新聚合根）
    attachment_id UUID NOT NULL,                           -- 解析出的新聚合根
    attachment_version_id UUID NOT NULL,                   -- 解析出的确定版本（永不 id-only / 静默 current）
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER NOT NULL,
    resolution_kind VARCHAR(20) NOT NULL,                  -- root | current_version | historical_version
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_legacy_alias_resolution_kind
        CHECK (resolution_kind IN ('root','current_version','historical_version'))
);

-- 复合 scope FK：别名指向的聚合根必须同 scope（design §4.1 "复合 scope FK"）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_legacy_alias_attachment_scope') THEN
        ALTER TABLE legacy_attachment_alias ADD CONSTRAINT fk_legacy_alias_attachment_scope
            FOREIGN KEY (attachment_id, project_id, audit_year)
            REFERENCES attachments(id, project_id, audit_year) ON DELETE RESTRICT;
    END IF;
END $$;

-- 复合 scope FK：别名指向的确定版本必须属于同一聚合根 + scope
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_legacy_alias_version_scope') THEN
        ALTER TABLE legacy_attachment_alias ADD CONSTRAINT fk_legacy_alias_version_scope
            FOREIGN KEY (attachment_version_id, attachment_id, project_id, audit_year)
            REFERENCES attachment_versions(id, attachment_id, project_id, audit_year) ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_legacy_alias_root ON legacy_attachment_alias(attachment_id);
CREATE INDEX IF NOT EXISTS idx_legacy_alias_scope ON legacy_attachment_alias(project_id, audit_year);

COMMENT ON TABLE legacy_attachment_alias IS 'design §4.1 旧附件 ID 别名解析：old_attachment_id → (新聚合根 attachment_id, 确定版本 attachment_version_id)；old ID 不假设等于新聚合根/当前版本';
COMMENT ON COLUMN legacy_attachment_alias.resolution_kind IS 'root | current_version | historical_version（LegacyResolutionKind 单一真源 contracts.py）';

-- ============================================================
-- 1. evidence_refs —— 持久 EvidenceRef（design §4.4；R3.1）
--    可查询、可保留的持久记录（非 per-request DTO）。活动引用 partial unique
--    (project_id,audit_year,intent_hash) WHERE status='active'（P7）。反向关系不复制，
--    使用 source / evidence 两套索引查询同一行（P8 双向一致）。
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_refs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER NOT NULL,
    -- 源 Controlled_Module（workpaper_cell / sampling_item / voucher / confirmation /
    -- review / note / report / ai / deliverable / attachment 等；异构 ID 用 text 承载）
    source_type VARCHAR(50) NOT NULL,
    source_id VARCHAR(200) NOT NULL,
    source_version VARCHAR(64),
    -- 目标证据对象
    evidence_type VARCHAR(50) NOT NULL,
    evidence_id VARCHAR(200) NOT NULL,
    attachment_version_id UUID REFERENCES attachment_versions(id) ON DELETE RESTRICT,
    target_version VARCHAR(64),
    target_hash VARCHAR(64),
    label VARCHAR(500),
    context JSONB,
    intent_hash VARCHAR(64) NOT NULL,                      -- canonical intent 哈希（活动幂等基准 P7）
    status VARCHAR(20) NOT NULL DEFAULT 'active',          -- active | inactive
    deactivation_reason TEXT,                              -- R3.4 停用需原因
    -- actor XOR（新表严格版：actor_type NOT NULL；contracts.validate_actor）
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    -- legacy created_by 兼容镜像（EVIDENCE_REF_PERSISTENT_COLUMNS 冻结列；非新写真源）
    created_by UUID REFERENCES users(id) ON DELETE RESTRICT,
    original_creator_unknown BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_evidence_ref_status CHECK (status IN ('active','inactive')),
    CONSTRAINT chk_evidence_ref_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

-- 活动 intent partial unique（P7：同一引用意图重复只保留一个活动引用）
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_ref_active_intent
    ON evidence_refs (project_id, audit_year, intent_hash)
    WHERE status = 'active';

-- 双向查询索引（P8）：源端 + 证据端，不复制反向关系
CREATE INDEX IF NOT EXISTS idx_evidence_ref_source
    ON evidence_refs (project_id, audit_year, source_type, source_id, status);
CREATE INDEX IF NOT EXISTS idx_evidence_ref_evidence
    ON evidence_refs (project_id, audit_year, evidence_type, evidence_id, status);
CREATE INDEX IF NOT EXISTS idx_evidence_ref_attachment_version
    ON evidence_refs (attachment_version_id);

COMMENT ON TABLE evidence_refs IS 'design §4.4 持久 EvidenceRef（非 per-request DTO）：绑定 scope/目标/版本/hash/意图/状态/actor；活动 intent partial unique + source/evidence 双向索引';
COMMENT ON COLUMN evidence_refs.intent_hash IS 'canonical intent 哈希（frozen_contracts.content_hash_of）；活动幂等基准，见 uq_evidence_ref_active_intent';
COMMENT ON COLUMN evidence_refs.created_by IS 'legacy 兼容镜像列（EVIDENCE_REF_PERSISTENT_COLUMNS 冻结）；新写真源是 actor_* XOR';

-- ============================================================
-- 2. evidence_dependencies —— 统一依赖图的动态边（design §4.4；R9/P20）
--    source→target（source 变化使 target stale），含 scope/版本/ACNR addr_id/relation/
--    canonical edge_hash/status/EvidenceRef FK/actor。同一逻辑边按 canonical edge hash 去重。
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER NOT NULL,
    -- source→target：source 变化使 target stale（异构节点用 type+id 承载）
    source_type VARCHAR(50) NOT NULL,
    source_id VARCHAR(200) NOT NULL,
    source_version VARCHAR(64),
    target_type VARCHAR(50) NOT NULL,
    target_id VARCHAR(200) NOT NULL,
    target_version VARCHAR(64),
    acnr_addr_id VARCHAR(300),                             -- 规范化 ACNR 地址（统一图 node key provenance）
    relation VARCHAR(50) NOT NULL,                         -- 边语义（derived_from / cites / writes_back 等）
    edge_hash VARCHAR(64) NOT NULL,                        -- canonical edge hash（同一逻辑边去重 P20）
    status VARCHAR(20) NOT NULL DEFAULT 'active',          -- active | inactive
    evidence_ref_id UUID REFERENCES evidence_refs(id) ON DELETE RESTRICT,
    -- actor XOR（新表严格版）
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_evidence_dep_status CHECK (status IN ('active','inactive')),
    CONSTRAINT chk_evidence_dep_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

-- canonical edge hash 去重：活动边按 (scope, edge_hash) partial unique（P7/P20 同一逻辑边一条活动边）
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_dep_active_edge
    ON evidence_dependencies (project_id, audit_year, edge_hash)
    WHERE status = 'active';

-- 双向遍历索引：正向（按 source 找下游 target 求闭包）+ 反向（按 target 找上游）
CREATE INDEX IF NOT EXISTS idx_evidence_dep_source
    ON evidence_dependencies (project_id, audit_year, source_type, source_id, status);
CREATE INDEX IF NOT EXISTS idx_evidence_dep_target
    ON evidence_dependencies (project_id, audit_year, target_type, target_id, status);
-- canonical edge hash 查重索引（含非活动，供去重/审计查询）
CREATE INDEX IF NOT EXISTS idx_evidence_dep_edge_hash
    ON evidence_dependencies (project_id, audit_year, edge_hash);
CREATE INDEX IF NOT EXISTS idx_evidence_dep_evidence_ref
    ON evidence_dependencies (evidence_ref_id);

COMMENT ON TABLE evidence_dependencies IS 'design §4.4 统一依赖图动态边 source→target；canonical edge_hash 去重 + 双向索引；与规范化 ACNR/legacy 边并集构成 UnifiedGraph（P20）';
COMMENT ON COLUMN evidence_dependencies.edge_hash IS 'canonical edge hash（frozen_contracts.content_hash_of）；同一逻辑边去重，见 uq_evidence_dep_active_edge';
