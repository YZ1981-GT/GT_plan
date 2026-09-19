-- V106: Evidence Governance — ServiceIdentity / actor XOR / UploadAttempt / quarantine-staging /
--       Attachment 聚合复合 scope key + 不可变 AttachmentVersion（循环 FK 分阶段 + deferrable 约束触发器 + immutable 触发器）
-- Spec: attachment-ocr-ai-evidence-governance-hardening / Task 2.2 (Wave 1)
-- Requirements: R1（附件接收安全与责任主体）, R2（证据元数据与不可变版本）, R12（审计/失败尝试最小审计）, R13（Legal Hold / ON DELETE RESTRICT）
-- Design: §Data Models(actor XOR), §4.0(UploadAttempt/失败审计/隔离区), §4.1(旧 ID 解析前置), §4.2(Attachment 聚合), §4.3(AttachmentVersion 复合约束/循环 FK 分阶段/immutable)
-- Properties: P3(actor 完备), P4(版本不可变), P5(哈希绑定), P25(command-root), P26(hold RESTRICT)
--
-- 约定（migration_allocation.lint_migration_sql 守卫，design §8.1）：
--   * additive-only：不删除任何表/列（不含 DROP TABLE/DROP COLUMN/TRUNCATE）。
--   * 可重复检测（幂等）：CREATE TABLE/INDEX 用 IF NOT EXISTS；ADD COLUMN 用 IF NOT EXISTS；
--     ADD CONSTRAINT / CONSTRAINT TRIGGER 用 pg_constraint / pg_trigger 存在性 DO 守卫；
--     函数用 CREATE OR REPLACE FUNCTION；immutable 触发器用 CREATE OR REPLACE TRIGGER。
--   * 所有内联 FK 默认 ON DELETE RESTRICT（回滚不级联删除治理对象）。
--
-- 单一真源（契约）：app.services.evidence_governance.contracts
--   （ACTOR_COLUMNS / validate_actor / LEGACY_ALIAS_COLUMNS / OCR_* 见 Task 1.3 冻结文档）。
-- 循环 FK 分阶段（design §4.3）：本迁移在单一事务内按顺序建 Attachment(不含 current_version 复合 FK)
--   → AttachmentVersion(复合 unique + 父 scope FK + previous 复合 FK DEFERRABLE)
--   → 再给 Attachment 加 current_version 复合 FK DEFERRABLE → deferrable 约束触发器 → immutable 触发器。

-- ============================================================
-- 0. ServiceIdentity —— 可追溯系统作业主体（不等同人工用户，不能执行人工确认）
-- ============================================================

CREATE TABLE IF NOT EXISTS service_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    identity_key VARCHAR(100) NOT NULL UNIQUE,        -- 稳定键，如 'migration' / 'ocr-worker' / 'finalize-worker'
    display_name VARCHAR(200) NOT NULL,
    kind VARCHAR(30) NOT NULL DEFAULT 'system',       -- system | worker | migration
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE service_identities IS 'evidence-governance 系统作业主体（Service Identity）；actor XOR 的 service 侧 FK 目标；永不获得人工确认/复核关闭/hold 解除/QC-EQCR 完成/signoff 能力';

-- 迁移专用 Service Identity（历史 created_by 无法证明时使用 + original_creator_unknown 标记；design §Data Models / R14.4）
INSERT INTO service_identities (identity_key, display_name, kind, description)
VALUES ('migration', 'Evidence Governance Migration', 'migration', '历史回填/迁移专用系统主体；不冒充人工用户')
ON CONFLICT (identity_key) DO NOTHING;

-- ============================================================
-- 1. UploadAttempt —— 每次上传在任何内容验证前创建的最小审计记录（design §4.0 / R1.1 / R12）
--    原始未清洗文件名、绝对路径、凭据、恶意文件正文不得进入本记录。
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_upload_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    sanitized_file_name VARCHAR(500) NOT NULL,        -- 已清洗文件名（非原始/绝对路径）
    declared_media_type VARCHAR(100),                 -- 客户端声明类型
    detected_media_type VARCHAR(100),                 -- 安全 magic 识别的实际类型（尚未可得时 NULL）
    received_byte_size BIGINT,                         -- 已接收字节数（流式累加，尚未可得时 NULL）
    content_hash VARCHAR(64),                          -- SHA-256（计算完成后更新，尚未可得时 NULL）
    validation_outcome VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending→accepted|rejected|quarantined|failed
    failure_category VARCHAR(50),                      -- 明确失败类别（empty/too_large/bad_name/type_not_allowed/type_mismatch/missing_actor/...）
    -- actor XOR（新表，无 legacy 行 → 严格：actor_type NOT NULL）
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    command_root_id UUID,                              -- 关联 EvidenceAuditCommandRoot（该表 Task 2.4 建，此处不加 FK）
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_upload_attempt_outcome
        CHECK (validation_outcome IN ('pending','accepted','rejected','quarantined','failed')),
    CONSTRAINT chk_upload_attempt_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_upload_attempt_scope ON evidence_upload_attempts(project_id, audit_year);
CREATE INDEX IF NOT EXISTS idx_upload_attempt_outcome ON evidence_upload_attempts(project_id, validation_outcome);
CREATE INDEX IF NOT EXISTS idx_upload_attempt_command_root ON evidence_upload_attempts(command_root_id);

COMMENT ON TABLE evidence_upload_attempts IS 'design §4.0 UploadAttempt：内容验证前的最小上传审计；失败尝试保留 outcome 但不创建可用 Attachment/Version';
COMMENT ON COLUMN evidence_upload_attempts.validation_outcome IS 'pending → accepted | rejected | quarantined | failed（同一 attempt 更新，不另建匿名尝试）';

-- ============================================================
-- 2. Quarantine / Staging handle —— 隔离/暂存句柄（不可公开读取；design §4.0）
--    无效/恶意/完整性失败内容不得成为可访问文件；is_publicly_readable 恒为 false（CHECK 强制）。
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_quarantine_handles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_attempt_id UUID NOT NULL REFERENCES evidence_upload_attempts(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    audit_year INTEGER,
    storage_key VARCHAR(500) NOT NULL,                 -- opaque 隔离/暂存 key（不出服务边界，不可公开读取）
    handle_state VARCHAR(20) NOT NULL DEFAULT 'staged',-- staged | quarantined | purged | promoted
    content_hash VARCHAR(64),
    byte_size BIGINT,
    detected_media_type VARCHAR(100),
    is_publicly_readable BOOLEAN NOT NULL DEFAULT false,
    purged_at TIMESTAMPTZ,                              -- 删除/加密擦除时间
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_identity_id UUID REFERENCES service_identities(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_quarantine_state
        CHECK (handle_state IN ('staged','quarantined','purged','promoted')),
    CONSTRAINT chk_quarantine_not_public CHECK (is_publicly_readable = false),
    CONSTRAINT chk_quarantine_actor_xor CHECK (
        (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
        OR
        (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_quarantine_attempt ON evidence_quarantine_handles(upload_attempt_id);
CREATE INDEX IF NOT EXISTS idx_quarantine_scope_state ON evidence_quarantine_handles(project_id, handle_state);

COMMENT ON TABLE evidence_quarantine_handles IS 'design §4.0 隔离/暂存句柄：内容不可经附件下载/预览/EvidenceRef/OCR/AI/FormalOutput/archive 访问；is_publicly_readable 恒 false';

-- ============================================================
-- 3. Attachment 聚合根 —— 在既有 legacy `attachments` 表上 additive 扩展治理列（design §4.2）
--    legacy file_name/file_path/file_type/file_size/ocr_status/version/previous_version_id/created_by
--    保留为只读兼容镜像（不删除、不改语义）。新增复合 scope key UNIQUE(id,project_id,audit_year)。
--    循环 FK 分阶段：此处先不加 current_version_id 的复合 FK（AttachmentVersion 建成后再加）。
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

-- state 域约束（NOT VALID：legacy 行默认 'available' 已合法，此处仅约束新写值域）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_attachments_state') THEN
        ALTER TABLE attachments ADD CONSTRAINT chk_attachments_state
            CHECK (state IN ('pending','available','inactive','tombstoned'));
    END IF;
END $$;

-- actor XOR（宽松版：允许 legacy 行 actor_type IS NULL 被祖父化；治理服务对新记录强制非空 XOR，见 contracts.validate_actor）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_attachments_actor_xor') THEN
        ALTER TABLE attachments ADD CONSTRAINT chk_attachments_actor_xor CHECK (
            actor_type IS NULL   -- legacy 兼容祖父化（dark-read M0）；no-anonymous 由服务层强制
            OR (actor_type = 'user'    AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL)
            OR (actor_type = 'service' AND actor_user_id IS NULL     AND actor_service_identity_id IS NOT NULL)
        );
    END IF;
END $$;

-- actor FK（分开 ADD CONSTRAINT，均 ON DELETE RESTRICT）
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

-- 父复合 scope key：UNIQUE(id, project_id, audit_year)（id 已是 PK，复合恒满足既有行，additive 安全）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_attachments_scope') THEN
        ALTER TABLE attachments ADD CONSTRAINT uq_attachments_scope
            UNIQUE (id, project_id, audit_year);
    END IF;
END $$;

COMMENT ON COLUMN attachments.state IS 'pending|available|inactive|tombstoned；只有 available 且当前版本 available 才可新建正式引用（design §4.2）';
COMMENT ON COLUMN attachments.current_version_id IS '初建可 NULL；finalize 后设置；复合 FK 见 uq_av_scope_identity（循环 FK 分阶段 DEFERRABLE）';

-- ============================================================
-- 4. AttachmentVersion —— 不可变内容快照（design §4.3）
-- ============================================================

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
    availability VARCHAR(20) NOT NULL DEFAULT 'staged',   -- staged | available | quarantined | inactive
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

-- (design §4.3 step 2) 复合身份 unique + 每附件版本号唯一
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

-- (design §4.3 step 7) 冗余 UNIQUE(attachment_id,content_hash,version_no) 有意不创建；
-- content_hash 仅建普通索引用于查重。
CREATE INDEX IF NOT EXISTS idx_av_content_hash ON attachment_versions(attachment_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_av_scope ON attachment_versions(project_id, audit_year);
CREATE INDEX IF NOT EXISTS idx_av_availability ON attachment_versions(attachment_id, availability);

-- (design §4.3 step 3) 父 scope FK：(attachment_id,project_id,audit_year) → attachments(id,project_id,audit_year)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_av_parent_scope') THEN
        ALTER TABLE attachment_versions ADD CONSTRAINT fk_av_parent_scope
            FOREIGN KEY (attachment_id, project_id, audit_year)
            REFERENCES attachments(id, project_id, audit_year) ON DELETE RESTRICT;
    END IF;
END $$;

-- (design §4.3 step 4) 前序复合 FK（DEFERRABLE INITIALLY DEFERRED；NULL 时整组按约束允许）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_av_previous_scope') THEN
        ALTER TABLE attachment_versions ADD CONSTRAINT fk_av_previous_scope
            FOREIGN KEY (previous_version_id, attachment_id, project_id, audit_year)
            REFERENCES attachment_versions(id, attachment_id, project_id, audit_year) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

COMMENT ON TABLE attachment_versions IS 'design §4.3 不可变内容快照；旧版本字节/key/hash/actor/time/attachment_id/version_no 由 trigger 禁止 UPDATE';

-- ============================================================
-- 5. 循环 FK 收口：给 Attachment 加 current_version 复合 FK（DEFERRABLE INITIALLY DEFERRED；design §4.3 step 5）
--    (current_version_id,id,project_id,audit_year) → attachment_versions(id,attachment_id,project_id,audit_year)
-- ============================================================

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_attachments_current_version') THEN
        ALTER TABLE attachments ADD CONSTRAINT fk_attachments_current_version
            FOREIGN KEY (current_version_id, id, project_id, audit_year)
            REFERENCES attachment_versions(id, attachment_id, project_id, audit_year) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

-- ============================================================
-- 6. Deferrable 约束触发器（提交时验证；design §4.3 step 6）
--    a) AttachmentVersion.previous_version_id：不得自指，且须同聚合根+scope。
--    b) Attachment.current_version_id：须属同聚合根+scope，且目标版本 availability='available'。
-- ============================================================

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

-- ============================================================
-- 7. Immutable 触发器（design §4.3 step 8）：禁止 UPDATE 旧版本的
--    字节(byte_size)/key(storage_key)/hash(content_hash)/actor(3列)/time(created_at)/attachment_id/version_no。
--    可变列：availability（staged→available）、previous_version_id、config_snapshot、media_type。
-- ============================================================

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
        RAISE EXCEPTION 'attachment_versions 不可变列（byte_size/storage_key/content_hash/actor_*/created_at/attachment_id/version_no）禁止 UPDATE (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_av_immutable
    BEFORE UPDATE ON attachment_versions
    FOR EACH ROW EXECUTE FUNCTION evgov_attachment_version_immutable();
