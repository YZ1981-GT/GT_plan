-- V151: 底稿 HTML ↔ OnlyOffice 双向回写 —— 统一内容版本域、definition bundle、
--       content application、room/request/close-intent/recovery、scope index 与逐 scenario evidence
--
-- Spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 9
-- Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 3.1, 3.6, 3.7, 4.1, 4.11, 5.4, 5.5, 5.10, 8.1, 12.10, 12.11, 13.5
-- Design: §Data Model 全节（working_paper 增量列 → evidence scenario）
-- Properties: P4（业务 revision ⊥ representation generation）、P5（无悬空可见态）、
--             P10（单次业务 commit 与 representation 幂等）、P11（唯一 descriptor + ready 确认）、
--             P18（delivery 可多次 / frozen application 恰一次）、P62（server last-applied ≠ client-confirmed base）、
--             P64（application identity 用 frozen bundle 且不含 status）、P68（timeline 完整单调）、
--             P69（evidence 由逐 scenario 实体闭合）
--
-- 迁移号实扫（实施前，2026-08-25）：backend/migrations 共 150 个 V*.sql，最大号 V150
-- （V150__ai_chat_message_seq_default_backfill.sql）⇒ 本迁移为 V151，无撞号。
-- R1xx__ 是配对回滚脚本，不占用 V 号。配对回滚：R151__rollback_workpaper_sync_content_application_bundle_scope.sql
--
-- ═══════════════════════════════════════════════════════════════════════════
-- 约定
-- ═══════════════════════════════════════════════════════════════════════════
-- 1. MigrationRunner 把整个文件放在**一个事务**里逐语句执行 ⇒ 本文件不写 BEGIN/COMMIT，
--    也不使用 PG enum（同事务内 `ALTER TYPE ADD VALUE` 后不可立即使用），一律 VARCHAR + CHECK。
-- 2. 幂等：CREATE TABLE/INDEX 用 IF NOT EXISTS；ADD COLUMN 用 IF NOT EXISTS；
--    ADD CONSTRAINT / CONSTRAINT TRIGGER 用 pg_constraint / pg_trigger 存在性 DO 守卫；
--    函数用 CREATE OR REPLACE FUNCTION；普通触发器用 CREATE OR REPLACE TRIGGER。
-- 3. additive-only：不 DROP 任何既有表/列，不 TRUNCATE，不改任何业务值。
-- 4. 回填只写 revision 0 台账（`working_paper_content_revision_backfill_ledger`）与
--    `content_revision=0` 默认值；**不创建 content version / representation / artifact**、
--    不写模板库、不引用模板文件。无法形成合法 approved bundle 的 entry 因此保持
--    single/unverified（台账 `entry_verification_state='unverified'`）。
-- 5. digest 单一真源 = `wpsync_is_digest()`：非空 + 64 位小写 hex + 非全零。所有 char(64)
--    身份列的 CHECK 都调用它 ⇒ SQL NULL / JSON null / 空串 / 全零 hash 无法充当身份。
-- 6. 建表顺序按 FK 依赖拓扑；room ↔ application 的循环 FK 分阶段（application 建成后
--    再给 room 加 DEFERRABLE FK）。
--
-- ═══════════════════════════════════════════════════════════════════════════
-- 0. 公共谓词函数（digest / opaque id 单一真源）
-- ═══════════════════════════════════════════════════════════════════════════

-- digest 合法性单一真源：SQL NULL、空串（含 bpchar 空白填充）、非 hex、大写、
-- 长度不足与全零 hash 一律非法。bpchar → text 隐式转换剥尾部空格，故
-- `''::char(64)` 在此退化为 ''，regex 不匹配 ⇒ 拒绝。
CREATE OR REPLACE FUNCTION wpsync_is_digest(p_value text) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT p_value IS NOT NULL
       AND p_value ~ '^[0-9a-f]{64}$'
       AND p_value <> repeat('0', 64);
$fn$;

COMMENT ON FUNCTION wpsync_is_digest(text) IS
    'V151 digest 单一真源：非空 + 64 位小写 hex + 非全零；bundle typed slot / application key / fingerprint 等身份列的 CHECK 全部调用它';

-- scope index 的 resource_id 必须是不可变 opaque identity；纯数字（numeric revision）
-- 禁止作为 scope/resource/route key（design §working_paper_sync_scope_index）。
CREATE OR REPLACE FUNCTION wpsync_is_opaque_resource_id(p_value text) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT p_value IS NOT NULL
       AND length(btrim(p_value)) > 0
       AND p_value !~ '^\s*[0-9]+\s*$';
$fn$;

COMMENT ON FUNCTION wpsync_is_opaque_resource_id(text) IS
    'V151：scope index resource_id 必须为不可变 opaque id（UUID/doc_key 等）；纯数字 numeric revision 一律拒绝，防跨 wp revision 碰撞';

CREATE OR REPLACE FUNCTION wpsync_is_uuid_text(p_value text) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT p_value IS NOT NULL
       AND p_value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$';
$fn$;

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. working_paper 增量列（design §`working_paper` 增量列 / Requirement 2.1）
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS content_revision BIGINT NOT NULL DEFAULT 0;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS current_content_version_id UUID;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_wp_content_revision_non_negative') THEN
        ALTER TABLE working_paper ADD CONSTRAINT ck_wp_content_revision_non_negative
            CHECK (content_revision >= 0);
    END IF;
END $$;

COMMENT ON COLUMN working_paper.content_revision IS
    'V151 业务内容 revision：只因业务 projection/custom 权威内容应用递增；纯 template/instrumentation/contract/authority-model/bundle/representation generation 变化不得推进（Requirement 2.1 / Property 4）';
COMMENT ON COLUMN working_paper.current_content_version_id IS
    'V151 当前 immutable business content version（FK 见 fk_wp_current_content_version，DEFERRABLE）';

-- ═══════════════════════════════════════════════════════════════════════════
-- 2. working_paper_artifact（design §working_paper_artifact / Requirement 2.4 / 5.6）
--    incoming 永不 published/current/resolvable；durable 与 quarantined 两支不可互转。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_artifact (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    kind VARCHAR(30) NOT NULL,
    state VARCHAR(20) NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL,
    document_type VARCHAR(20) NOT NULL,
    retention_class VARCHAR(40) NOT NULL DEFAULT 'default',
    legal_hold BOOLEAN NOT NULL DEFAULT false,
    source_delivery_id UUID,
    created_by_operation_id UUID,
    durable_at TIMESTAMPTZ,
    quarantined_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    orphaned_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_wpa_kind CHECK (kind IN (
        'canonical', 'upgrade_candidate', 'incoming', 'projection',
        'definition', 'template', 'evidence', 'trace_bundle')),
    CONSTRAINT ck_wpa_state CHECK (state IN (
        'staged', 'durable', 'candidate', 'published', 'orphan', 'quarantined', 'deleted')),
    CONSTRAINT ck_wpa_sha256 CHECK (wpsync_is_digest(sha256)),
    CONSTRAINT ck_wpa_size_non_negative CHECK (size_bytes >= 0),
    CONSTRAINT ck_wpa_document_type CHECK (document_type IN ('xlsx', 'docx', 'json.gz', 'json', 'zip')),
    -- incoming 永不 published/candidate（resolver 永不返回 incoming；Requirement 5.6）
    CONSTRAINT ck_wpa_incoming_never_published CHECK (
        kind <> 'incoming' OR state IN ('staged', 'durable', 'quarantined', 'orphan', 'deleted')),
    -- upgrade_candidate 永不 published/durable（Requirement 3.4 / Property 5）
    CONSTRAINT ck_wpa_candidate_never_published CHECK (
        kind <> 'upgrade_candidate' OR state IN ('staged', 'candidate', 'orphan', 'deleted')),
    -- incoming 至少有 delivery；recovery incoming 不要求 operation
    CONSTRAINT ck_wpa_incoming_requires_delivery CHECK (
        kind <> 'incoming' OR source_delivery_id IS NOT NULL),
    -- durable 与 quarantined 互斥；quarantined 保持 durable_at=NULL
    CONSTRAINT ck_wpa_durable_quarantine_exclusive CHECK (
        durable_at IS NULL OR quarantined_at IS NULL),
    CONSTRAINT ck_wpa_quarantined_state_no_durable_at CHECK (
        state <> 'quarantined' OR durable_at IS NULL),
    CONSTRAINT ck_wpa_durable_state_has_durable_at CHECK (
        state <> 'durable' OR durable_at IS NOT NULL),
    CONSTRAINT ck_wpa_published_state_has_published_at CHECK (
        state <> 'published' OR published_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_wpa_scope ON working_paper_artifact (project_id, wp_id);
CREATE INDEX IF NOT EXISTS idx_wpa_kind_state ON working_paper_artifact (kind, state);
CREATE INDEX IF NOT EXISTS idx_wpa_sha256 ON working_paper_artifact (sha256);
CREATE INDEX IF NOT EXISTS idx_wpa_delivery ON working_paper_artifact (source_delivery_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_wpa_relative_path ON working_paper_artifact (relative_path);

COMMENT ON TABLE working_paper_artifact IS
    'V151 内容寻址不可变 artifact 台账；incoming 只能 staged→durable 或 staged→quarantined，两支不可互转，永不 published/current/resolvable（Requirement 5.6 / Property 5）';

-- incoming sealing 路径以 delivery identity 固定为 `.incoming/{wp_id}/{delivery_id}/`，
-- 不依赖 operation/application（design §Filesystem Layout；Task 9 硬判据）。
CREATE OR REPLACE FUNCTION wpsync_check_artifact_incoming_path() RETURNS trigger AS $fn$
DECLARE
    v_expected text;
BEGIN
    IF NEW.kind <> 'incoming' THEN
        RETURN NEW;
    END IF;
    IF NEW.source_delivery_id IS NULL THEN
        RAISE EXCEPTION 'incoming artifact 必须绑定 source_delivery_id (artifact=%)', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    v_expected := '.incoming/' || NEW.wp_id::text || '/' || NEW.source_delivery_id::text || '/';
    IF position(v_expected in NEW.relative_path) = 0 THEN
        RAISE EXCEPTION 'incoming artifact 路径必须以 delivery identity sealing（期望片段 %，实得 %）', v_expected, NEW.relative_path
            USING ERRCODE = 'check_violation';
    END IF;
    -- 路径不得依赖 operation/application
    IF NEW.created_by_operation_id IS NOT NULL
       AND position(NEW.created_by_operation_id::text in NEW.relative_path) > 0 THEN
        RAISE EXCEPTION 'incoming artifact 路径不得包含 operation id（路径只依赖 delivery identity）: %', NEW.relative_path
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpa_incoming_path
    BEFORE INSERT OR UPDATE ON working_paper_artifact
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_artifact_incoming_path();

-- artifact 允许状态边 + 内容身份不可变
CREATE OR REPLACE FUNCTION wpsync_check_artifact_transition() RETURNS trigger AS $fn$
BEGIN
    IF NEW.sha256 IS DISTINCT FROM OLD.sha256
       OR NEW.relative_path IS DISTINCT FROM OLD.relative_path
       OR NEW.kind IS DISTINCT FROM OLD.kind
       OR NEW.wp_id IS DISTINCT FROM OLD.wp_id
       OR NEW.project_id IS DISTINCT FROM OLD.project_id
       OR NEW.size_bytes IS DISTINCT FROM OLD.size_bytes THEN
        RAISE EXCEPTION 'working_paper_artifact 内容身份列（kind/sha256/relative_path/size/scope）不可变 (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.kind = 'incoming' THEN
        IF OLD.state = 'durable' AND NEW.state = 'quarantined' THEN
            RAISE EXCEPTION 'incoming artifact durable→quarantined 非法：durable 与 quarantined 两支不可互转 (id=%)', OLD.id
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.state = 'quarantined' AND NEW.state = 'durable' THEN
            RAISE EXCEPTION 'incoming artifact quarantined→durable 非法：quarantined 永不 release/转 durable (id=%)', OLD.id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpa_transition
    BEFORE UPDATE ON working_paper_artifact
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_artifact_transition();

-- ═══════════════════════════════════════════════════════════════════════════
-- 3. working_paper_sync_definition_artifact（design §同名节 / Requirement 2.3）
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_sync_definition_artifact (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(20) NOT NULL,
    logical_id VARCHAR(200) NOT NULL,
    semantic_version VARCHAR(50) NOT NULL,
    blob_artifact_id UUID NOT NULL REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    sha256 CHAR(64) NOT NULL,
    structure_hash CHAR(64),
    authority_model_type VARCHAR(40),
    source_commit VARCHAR(80) NOT NULL,
    supersedes_id UUID REFERENCES working_paper_sync_definition_artifact(id) ON DELETE RESTRICT,
    state VARCHAR(20) NOT NULL DEFAULT 'candidate',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    CONSTRAINT ck_wpsda_kind CHECK (kind IN ('template', 'instrumentation', 'contract', 'authority_model')),
    CONSTRAINT ck_wpsda_state CHECK (state IN ('candidate', 'approved', 'retired')),
    CONSTRAINT ck_wpsda_sha256 CHECK (wpsync_is_digest(sha256)),
    CONSTRAINT ck_wpsda_structure_hash CHECK (structure_hash IS NULL OR wpsync_is_digest(structure_hash)),
    CONSTRAINT ck_wpsda_no_self_supersede CHECK (supersedes_id IS NULL OR supersedes_id <> id),
    CONSTRAINT ck_wpsda_approved_at CHECK (state <> 'approved' OR approved_at IS NOT NULL),
    -- 🔴 三值逻辑：必须显式 `IS NOT NULL`。只写 `type IN (...)` 时 NULL 会让整条
    --    CHECK 求值为 NULL（= 视为满足），authority_model 缺枚举将被静默放行。
    CONSTRAINT ck_wpsda_authority_model_type CHECK (
        (kind = 'authority_model'
            AND authority_model_type IS NOT NULL
            AND authority_model_type IN ('projection_contract', 'custom_authoritative_ooxml', 'opaque_single_onlyoffice'))
        OR (kind <> 'authority_model' AND authority_model_type IS NULL)),
    CONSTRAINT uq_wpsda_kind_sha256 UNIQUE (kind, sha256)
);

CREATE INDEX IF NOT EXISTS idx_wpsda_logical ON working_paper_sync_definition_artifact (kind, logical_id, semantic_version);
CREATE INDEX IF NOT EXISTS idx_wpsda_state ON working_paper_sync_definition_artifact (kind, state);

COMMENT ON TABLE working_paper_sync_definition_artifact IS
    'V151 immutable definition 快照（template/instrumentation/contract/authority_model）；registry alias 只解析到 approved row，历史引用保存 FK+digest 不随 alias 漂移';
COMMENT ON COLUMN working_paper_sync_definition_artifact.authority_model_type IS
    'kind=authority_model 时的封闭枚举投影（projection_contract/custom_authoritative_ooxml/opaque_single_onlyoffice），供 bundle trigger 在 DB 层锁死 child 规则';

CREATE OR REPLACE FUNCTION wpsync_check_definition_immutable() RETURNS trigger AS $fn$
BEGIN
    IF NEW.kind IS DISTINCT FROM OLD.kind
       OR NEW.sha256 IS DISTINCT FROM OLD.sha256
       OR NEW.blob_artifact_id IS DISTINCT FROM OLD.blob_artifact_id
       OR NEW.authority_model_type IS DISTINCT FROM OLD.authority_model_type THEN
        RAISE EXCEPTION 'definition artifact 身份列（kind/sha256/blob/authority_model_type）不可变 (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.state = 'approved' AND NEW.state = 'candidate' THEN
        RAISE EXCEPTION 'definition artifact approved→candidate 非法 (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpsda_immutable
    BEFORE UPDATE ON working_paper_sync_definition_artifact
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_definition_immutable();

-- ═══════════════════════════════════════════════════════════════════════════
-- 4. 版本化 typed null marker registry
--    optional child 只能使用 registry 中版本化 typed null marker 及其真实 digest。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_sync_definition_null_marker (
    marker_id VARCHAR(80) PRIMARY KEY,
    applies_to_slot VARCHAR(20) NOT NULL,
    marker_version VARCHAR(20) NOT NULL,
    canonical_payload TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL UNIQUE,
    state VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_wpsnm_slot CHECK (applies_to_slot IN ('template', 'instrumentation', 'contract')),
    CONSTRAINT ck_wpsnm_state CHECK (state IN ('active', 'retired')),
    CONSTRAINT ck_wpsnm_sha256 CHECK (wpsync_is_digest(sha256)),
    CONSTRAINT ck_wpsnm_payload_non_empty CHECK (length(btrim(canonical_payload)) > 0),
    CONSTRAINT ck_wpsnm_versioned_id CHECK (marker_id ~ '^(template|instrumentation|contract):none:v[0-9]+$')
);

COMMENT ON TABLE working_paper_sync_definition_null_marker IS
    'V151 版本化 typed null marker registry：bundle 的 optional child 只能引用本表 marker 及其真实 digest；slot omission / SQL NULL / 空串 / 全零 hash 一律拒绝';

-- digest 由 canonical payload 真实计算（不是人手填的基线）
INSERT INTO working_paper_sync_definition_null_marker
    (marker_id, applies_to_slot, marker_version, canonical_payload, sha256)
VALUES
    ('template:none:v1', 'template', 'v1',
     '{"schema_version":"definition-bundle-marker:v1","slot":"template","value":"none"}',
     encode(sha256(convert_to('{"schema_version":"definition-bundle-marker:v1","slot":"template","value":"none"}', 'UTF8')), 'hex')),
    ('instrumentation:none:v1', 'instrumentation', 'v1',
     '{"schema_version":"definition-bundle-marker:v1","slot":"instrumentation","value":"none"}',
     encode(sha256(convert_to('{"schema_version":"definition-bundle-marker:v1","slot":"instrumentation","value":"none"}', 'UTF8')), 'hex')),
    ('contract:none:v1', 'contract', 'v1',
     '{"schema_version":"definition-bundle-marker:v1","slot":"contract","value":"none"}',
     encode(sha256(convert_to('{"schema_version":"definition-bundle-marker:v1","slot":"contract","value":"none"}', 'UTF8')), 'hex'))
ON CONFLICT (marker_id) DO NOTHING;

CREATE OR REPLACE FUNCTION wpsync_check_null_marker_immutable() RETURNS trigger AS $fn$
BEGIN
    IF NEW.applies_to_slot IS DISTINCT FROM OLD.applies_to_slot
       OR NEW.canonical_payload IS DISTINCT FROM OLD.canonical_payload
       OR NEW.sha256 IS DISTINCT FROM OLD.sha256
       OR NEW.marker_version IS DISTINCT FROM OLD.marker_version THEN
        RAISE EXCEPTION 'typed null marker 不可变（slot/payload/sha256/version）: %', OLD.marker_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpsnm_immutable
    BEFORE UPDATE ON working_paper_sync_definition_null_marker
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_null_marker_immutable();

-- ═══════════════════════════════════════════════════════════════════════════
-- 5. working_paper_sync_definition_bundle（design §同名节 / Requirement 2.3 / 3.3）
--    authority model + template/instrumentation/contract 三个 typed slot 全部 NOT NULL；
--    CHECK + trigger 锁死 child kind/state/digest；projection_contract 必须三 child 全 approved definition。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_sync_definition_bundle (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schema_version VARCHAR(50) NOT NULL DEFAULT 'definition-bundle:v1',
    authority_model_definition_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_artifact(id) ON DELETE RESTRICT,
    authority_model_definition_sha256 CHAR(64) NOT NULL,
    template_slot_type VARCHAR(80) NOT NULL,
    template_slot_ref TEXT NOT NULL,
    template_slot_digest CHAR(64) NOT NULL,
    instrumentation_slot_type VARCHAR(80) NOT NULL,
    instrumentation_slot_ref TEXT NOT NULL,
    instrumentation_slot_digest CHAR(64) NOT NULL,
    contract_slot_type VARCHAR(80) NOT NULL,
    contract_slot_ref TEXT NOT NULL,
    contract_slot_digest CHAR(64) NOT NULL,
    canonical_payload_artifact_id UUID NOT NULL
        REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    canonical_payload_sha256 CHAR(64) NOT NULL UNIQUE,
    state VARCHAR(20) NOT NULL DEFAULT 'candidate',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    CONSTRAINT ck_wpsdb_state CHECK (state IN ('candidate', 'approved', 'retired')),
    CONSTRAINT ck_wpsdb_approved_at CHECK (state <> 'approved' OR approved_at IS NOT NULL),
    CONSTRAINT ck_wpsdb_schema_version CHECK (schema_version ~ '^definition-bundle:v[0-9]+$'),
    -- 五个身份 digest 全部必须是真实非空非零 hash（空串/全零/大写/短串全拒）
    CONSTRAINT ck_wpsdb_authority_digest CHECK (wpsync_is_digest(authority_model_definition_sha256)),
    CONSTRAINT ck_wpsdb_template_digest CHECK (wpsync_is_digest(template_slot_digest)),
    CONSTRAINT ck_wpsdb_instrumentation_digest CHECK (wpsync_is_digest(instrumentation_slot_digest)),
    CONSTRAINT ck_wpsdb_contract_digest CHECK (wpsync_is_digest(contract_slot_digest)),
    CONSTRAINT ck_wpsdb_canonical_digest CHECK (wpsync_is_digest(canonical_payload_sha256)),
    -- slot type：'definition' 或版本化 typed null marker id
    CONSTRAINT ck_wpsdb_template_slot_type CHECK (
        template_slot_type = 'definition' OR template_slot_type ~ '^template:none:v[0-9]+$'),
    CONSTRAINT ck_wpsdb_instrumentation_slot_type CHECK (
        instrumentation_slot_type = 'definition' OR instrumentation_slot_type ~ '^instrumentation:none:v[0-9]+$'),
    CONSTRAINT ck_wpsdb_contract_slot_type CHECK (
        contract_slot_type = 'definition' OR contract_slot_type ~ '^contract:none:v[0-9]+$'),
    -- slot ref：definition:<uuid> 或 marker:<versioned-id>；空串/JSON null 字面量一律拒绝
    CONSTRAINT ck_wpsdb_template_ref CHECK (
        template_slot_ref ~ '^definition:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        OR template_slot_ref ~ '^marker:template:none:v[0-9]+$'),
    CONSTRAINT ck_wpsdb_instrumentation_ref CHECK (
        instrumentation_slot_ref ~ '^definition:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        OR instrumentation_slot_ref ~ '^marker:instrumentation:none:v[0-9]+$'),
    CONSTRAINT ck_wpsdb_contract_ref CHECK (
        contract_slot_ref ~ '^definition:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        OR contract_slot_ref ~ '^marker:contract:none:v[0-9]+$'),
    -- type 与 ref 必须同为 definition 或同为同一 marker
    CONSTRAINT ck_wpsdb_template_type_ref_agree CHECK (
        (template_slot_type = 'definition' AND template_slot_ref LIKE 'definition:%')
        OR (template_slot_type <> 'definition' AND template_slot_ref = 'marker:' || template_slot_type)),
    CONSTRAINT ck_wpsdb_instrumentation_type_ref_agree CHECK (
        (instrumentation_slot_type = 'definition' AND instrumentation_slot_ref LIKE 'definition:%')
        OR (instrumentation_slot_type <> 'definition' AND instrumentation_slot_ref = 'marker:' || instrumentation_slot_type)),
    CONSTRAINT ck_wpsdb_contract_type_ref_agree CHECK (
        (contract_slot_type = 'definition' AND contract_slot_ref LIKE 'definition:%')
        OR (contract_slot_type <> 'definition' AND contract_slot_ref = 'marker:' || contract_slot_type))
);

CREATE INDEX IF NOT EXISTS idx_wpsdb_state ON working_paper_sync_definition_bundle (state);
CREATE INDEX IF NOT EXISTS idx_wpsdb_authority ON working_paper_sync_definition_bundle (authority_model_definition_id);

COMMENT ON TABLE working_paper_sync_definition_bundle IS
    'V151 frozen definition bundle：authority model + template/instrumentation/contract 四 slot 全 NOT NULL；projection_contract 必须三 child 全为 approved definition，custom/opaque 只能用 registry 版本化 typed null marker';

-- 单 slot 断言（definition / marker 两支）：解析 ref 并逐项校验 kind/state/digest。
-- 该函数是 DB 层与 service validator 共用的 slot 判据单一真源。
CREATE OR REPLACE FUNCTION wpsync_assert_bundle_slot(
    p_bundle_id uuid,
    p_slot text,
    p_slot_type text,
    p_slot_ref text,
    p_slot_digest text
) RETURNS void AS $fn$
DECLARE
    v_def_id uuid;
    v_kind text;
    v_state text;
    v_sha text;
    v_marker_lookup text;
    v_marker_id text;
    v_marker_slot text;
    v_marker_state text;
    v_marker_sha text;
BEGIN
    IF p_slot_type IS NULL OR p_slot_ref IS NULL OR p_slot_digest IS NULL THEN
        RAISE EXCEPTION 'bundle % 的 % slot 缺失（type/ref/digest 均不得为 NULL）', p_bundle_id, p_slot
            USING ERRCODE = 'check_violation';
    END IF;
    IF NOT wpsync_is_digest(p_slot_digest) THEN
        RAISE EXCEPTION 'bundle % 的 % slot digest 非法（空串/全零/非 hex 均拒绝）: [%]', p_bundle_id, p_slot, p_slot_digest
            USING ERRCODE = 'check_violation';
    END IF;

    IF p_slot_type = 'definition' THEN
        IF p_slot_ref NOT LIKE 'definition:%' THEN
            RAISE EXCEPTION 'bundle % 的 % slot type=definition 但 ref 非 definition 形态: %', p_bundle_id, p_slot, p_slot_ref
                USING ERRCODE = 'check_violation';
        END IF;
        v_def_id := substring(p_slot_ref from 12)::uuid;
        SELECT d.kind, d.state, d.sha256 INTO v_kind, v_state, v_sha
          FROM working_paper_sync_definition_artifact d WHERE d.id = v_def_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'bundle % 的 % slot 引用不存在的 definition %', p_bundle_id, p_slot, v_def_id
                USING ERRCODE = 'foreign_key_violation';
        END IF;
        IF v_kind <> p_slot THEN
            RAISE EXCEPTION 'bundle % 的 % slot child kind 不符（期望 %，实得 %）', p_bundle_id, p_slot, p_slot, v_kind
                USING ERRCODE = 'check_violation';
        END IF;
        IF v_state <> 'approved' THEN
            RAISE EXCEPTION 'bundle % 的 % slot child 必须 approved，实得 %', p_bundle_id, p_slot, v_state
                USING ERRCODE = 'check_violation';
        END IF;
        IF v_sha <> p_slot_digest THEN
            RAISE EXCEPTION 'bundle % 的 % slot digest 与 child 实际 sha256 不一致', p_bundle_id, p_slot
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN;
    END IF;

    -- marker 支：只接受 registry 中 active 的版本化 typed null marker 及其真实 digest
    v_marker_lookup := substring(p_slot_ref from 8);
    SELECT m.marker_id, m.applies_to_slot, m.state, m.sha256
      INTO v_marker_id, v_marker_slot, v_marker_state, v_marker_sha
      FROM working_paper_sync_definition_null_marker m WHERE m.marker_id = v_marker_lookup;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'bundle % 的 % slot 引用未登记的 typed null marker: %', p_bundle_id, p_slot, p_slot_ref
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_marker_slot <> p_slot THEN
        RAISE EXCEPTION 'bundle % 的 % slot 使用了 % 槽位的 marker', p_bundle_id, p_slot, v_marker_slot
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_marker_state <> 'active' THEN
        RAISE EXCEPTION 'bundle % 的 % slot marker 已 retired: %', p_bundle_id, p_slot, v_marker_id
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_marker_sha <> p_slot_digest THEN
        RAISE EXCEPTION 'bundle % 的 % slot marker digest 与 registry 不一致（禁止伪造 typed null digest）', p_bundle_id, p_slot
            USING ERRCODE = 'check_violation';
    END IF;
END;
$fn$ LANGUAGE plpgsql;

COMMENT ON FUNCTION wpsync_assert_bundle_slot(uuid, text, text, text, text) IS
    'V151 bundle typed slot 判据单一真源：definition 支校验 kind/state=approved/digest 等值，marker 支校验 registry 登记/槽位/active/真实 digest';

-- bundle 整体规则：authority model approved + 三 slot 合法 + projection_contract 必须三 definition child
CREATE OR REPLACE FUNCTION wpsync_check_bundle_slots() RETURNS trigger AS $fn$
DECLARE
    v_authority_kind text;
    v_authority_state text;
    v_authority_sha text;
    v_authority_model text;
BEGIN
    SELECT d.kind, d.state, d.sha256, d.authority_model_type
      INTO v_authority_kind, v_authority_state, v_authority_sha, v_authority_model
      FROM working_paper_sync_definition_artifact d
     WHERE d.id = NEW.authority_model_definition_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'bundle % 的 authority_model_definition_id % 不存在', NEW.id, NEW.authority_model_definition_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_authority_kind <> 'authority_model' THEN
        RAISE EXCEPTION 'bundle % 的 authority model child kind 必须为 authority_model，实得 %', NEW.id, v_authority_kind
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_authority_state <> 'approved' THEN
        RAISE EXCEPTION 'bundle % 的 authority model child 必须 approved，实得 %', NEW.id, v_authority_state
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_authority_sha <> NEW.authority_model_definition_sha256 THEN
        RAISE EXCEPTION 'bundle % 的 authority_model_definition_sha256 与 child 实际 digest 不一致', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM wpsync_assert_bundle_slot(NEW.id, 'template', NEW.template_slot_type, NEW.template_slot_ref, NEW.template_slot_digest);
    PERFORM wpsync_assert_bundle_slot(NEW.id, 'instrumentation', NEW.instrumentation_slot_type, NEW.instrumentation_slot_ref, NEW.instrumentation_slot_digest);
    PERFORM wpsync_assert_bundle_slot(NEW.id, 'contract', NEW.contract_slot_type, NEW.contract_slot_ref, NEW.contract_slot_digest);

    IF v_authority_model = 'projection_contract' THEN
        IF NEW.template_slot_type <> 'definition'
           OR NEW.instrumentation_slot_type <> 'definition'
           OR NEW.contract_slot_type <> 'definition' THEN
            RAISE EXCEPTION 'projection_contract bundle % 的 template/instrumentation/contract 三 slot 必须全为 approved definition（实得 %/%/%）',
                NEW.id, NEW.template_slot_type, NEW.instrumentation_slot_type, NEW.contract_slot_type
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpsdb_slots
    BEFORE INSERT OR UPDATE ON working_paper_sync_definition_bundle
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_bundle_slots();

-- approved bundle 不可修改或重组（历史 retry 直接读 bundle row）
CREATE OR REPLACE FUNCTION wpsync_check_bundle_immutable() RETURNS trigger AS $fn$
BEGIN
    IF NEW.authority_model_definition_id IS DISTINCT FROM OLD.authority_model_definition_id
       OR NEW.authority_model_definition_sha256 IS DISTINCT FROM OLD.authority_model_definition_sha256
       OR NEW.template_slot_type IS DISTINCT FROM OLD.template_slot_type
       OR NEW.template_slot_ref IS DISTINCT FROM OLD.template_slot_ref
       OR NEW.template_slot_digest IS DISTINCT FROM OLD.template_slot_digest
       OR NEW.instrumentation_slot_type IS DISTINCT FROM OLD.instrumentation_slot_type
       OR NEW.instrumentation_slot_ref IS DISTINCT FROM OLD.instrumentation_slot_ref
       OR NEW.instrumentation_slot_digest IS DISTINCT FROM OLD.instrumentation_slot_digest
       OR NEW.contract_slot_type IS DISTINCT FROM OLD.contract_slot_type
       OR NEW.contract_slot_ref IS DISTINCT FROM OLD.contract_slot_ref
       OR NEW.contract_slot_digest IS DISTINCT FROM OLD.contract_slot_digest
       OR NEW.canonical_payload_artifact_id IS DISTINCT FROM OLD.canonical_payload_artifact_id
       OR NEW.canonical_payload_sha256 IS DISTINCT FROM OLD.canonical_payload_sha256
       OR NEW.schema_version IS DISTINCT FROM OLD.schema_version THEN
        RAISE EXCEPTION 'definition bundle 的 authority model / typed slots / canonical payload 不可变，只允许 state 与 approved_at 推进 (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.state = 'approved' AND NEW.state = 'candidate' THEN
        RAISE EXCEPTION 'definition bundle approved→candidate 非法 (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpsdb_immutable
    BEFORE UPDATE ON working_paper_sync_definition_bundle
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_bundle_immutable();

-- ═══════════════════════════════════════════════════════════════════════════
-- 6. working_paper_content_version（design §同名节 / Requirement 2.1 / 2.3）
--    immutable；`revision` 只映射业务内容；opaque `id` 是唯一 resource/route key。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_content_version (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    revision BIGINT NOT NULL,
    parent_version_id UUID REFERENCES working_paper_content_version(id) ON DELETE RESTRICT,
    source VARCHAR(30) NOT NULL,
    projection_artifact_id UUID REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    projection_sha256 CHAR(64),
    authoritative_artifact_id UUID REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    authoritative_artifact_sha256 CHAR(64),
    operation_id UUID,
    actor_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpcv_wp_revision UNIQUE (wp_id, revision),
    CONSTRAINT ck_wpcv_revision_non_negative CHECK (revision >= 0),
    CONSTRAINT ck_wpcv_source CHECK (source IN ('html', 'onlyoffice', 'conflict_resolution', 'rollback', 'custom')),
    CONSTRAINT ck_wpcv_no_self_parent CHECK (parent_version_id IS NULL OR parent_version_id <> id),
    CONSTRAINT ck_wpcv_projection_digest CHECK (projection_sha256 IS NULL OR wpsync_is_digest(projection_sha256)),
    CONSTRAINT ck_wpcv_authoritative_digest CHECK (
        authoritative_artifact_sha256 IS NULL OR wpsync_is_digest(authoritative_artifact_sha256)),
    -- artifact 与 digest 必须成对出现（不得只留可漂移字符串或只留 FK）
    CONSTRAINT ck_wpcv_projection_pair CHECK (
        (projection_artifact_id IS NULL) = (projection_sha256 IS NULL)),
    CONSTRAINT ck_wpcv_authoritative_pair CHECK (
        (authoritative_artifact_id IS NULL) = (authoritative_artifact_sha256 IS NULL)),
    -- 至少一侧权威内容存在（标准结构化走 projection，custom/opaque 走 authoritative OOXML）
    CONSTRAINT ck_wpcv_has_content CHECK (
        projection_artifact_id IS NOT NULL OR authoritative_artifact_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_wpcv_wp ON working_paper_content_version (wp_id, revision DESC);
CREATE INDEX IF NOT EXISTS idx_wpcv_operation ON working_paper_content_version (operation_id);

COMMENT ON TABLE working_paper_content_version IS
    'V151 immutable business content version；numeric revision 只用于展示与 expected-current 乐观锁，scope/route 定位一律用 opaque id（Property 4 / design §Rollback）';

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_wp_current_content_version') THEN
        ALTER TABLE working_paper ADD CONSTRAINT fk_wp_current_content_version
            FOREIGN KEY (current_content_version_id)
            REFERENCES working_paper_content_version(id) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE OR REPLACE FUNCTION wpsync_check_content_version_immutable() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION 'working_paper_content_version 为 immutable 历史行，禁止 UPDATE (id=%)', OLD.id
        USING ERRCODE = 'check_violation';
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpcv_immutable
    BEFORE UPDATE ON working_paper_content_version
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_content_version_immutable();

-- ═══════════════════════════════════════════════════════════════════════════
-- 7. working_paper_content_representation（design §同名节）
--    同一业务 version 允许多个 generation；只能由 approved bundle finalize。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_content_representation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    content_version_id UUID NOT NULL REFERENCES working_paper_content_version(id) ON DELETE RESTRICT,
    entry_id VARCHAR(200) NOT NULL,
    generation BIGINT NOT NULL,
    parent_representation_id UUID REFERENCES working_paper_content_representation(id) ON DELETE RESTRICT,
    document_type VARCHAR(10) NOT NULL,
    artifact_id UUID NOT NULL REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    artifact_sha256 CHAR(64) NOT NULL,
    definition_bundle_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_bundle(id) ON DELETE RESTRICT,
    definition_bundle_sha256 CHAR(64) NOT NULL,
    authority_model_definition_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_artifact(id) ON DELETE RESTRICT,
    authority_model_definition_sha256 CHAR(64) NOT NULL,
    adapter_id VARCHAR(120) NOT NULL,
    adapter_build_digest CHAR(64) NOT NULL,
    structure_hash CHAR(64) NOT NULL,
    identity_inventory_sha256 CHAR(64) NOT NULL,
    reason VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpcr_generation UNIQUE (wp_id, entry_id, content_version_id, generation),
    CONSTRAINT ck_wpcr_generation_positive CHECK (generation >= 1),
    CONSTRAINT ck_wpcr_document_type CHECK (document_type IN ('xlsx', 'docx')),
    CONSTRAINT ck_wpcr_reason CHECK (reason IN ('content_commit', 'definition_upgrade', 'rollback', 'rematerialize')),
    CONSTRAINT ck_wpcr_no_self_parent CHECK (parent_representation_id IS NULL OR parent_representation_id <> id),
    CONSTRAINT ck_wpcr_artifact_digest CHECK (wpsync_is_digest(artifact_sha256)),
    CONSTRAINT ck_wpcr_bundle_digest CHECK (wpsync_is_digest(definition_bundle_sha256)),
    CONSTRAINT ck_wpcr_authority_digest CHECK (wpsync_is_digest(authority_model_definition_sha256)),
    CONSTRAINT ck_wpcr_adapter_digest CHECK (wpsync_is_digest(adapter_build_digest)),
    CONSTRAINT ck_wpcr_structure_hash CHECK (wpsync_is_digest(structure_hash)),
    CONSTRAINT ck_wpcr_identity_inventory CHECK (wpsync_is_digest(identity_inventory_sha256))
);

CREATE INDEX IF NOT EXISTS idx_wpcr_entry ON working_paper_content_representation (wp_id, entry_id, generation DESC);
CREATE INDEX IF NOT EXISTS idx_wpcr_bundle ON working_paper_content_representation (definition_bundle_id);

COMMENT ON TABLE working_paper_content_representation IS
    'V151 immutable representation generation：同一 content version 可有多个 generation（纯表示升级），只能由 approved bundle finalize，candidate 与 incoming 均不可成为 representation（Property 4/5）';

-- representation 的 bundle/authority/artifact 三重锁死：
--   1) bundle 必须 approved
--   2) authority model FK/digest 必须等于 bundle 的 authority child
--   3) artifact 必须 published 的 canonical/projection，绝不能是 incoming / upgrade_candidate
CREATE OR REPLACE FUNCTION wpsync_check_representation_identity() RETURNS trigger AS $fn$
DECLARE
    v_bundle_state text;
    v_bundle_sha text;
    v_bundle_authority_id uuid;
    v_bundle_authority_sha text;
    v_artifact_kind text;
    v_artifact_state text;
    v_artifact_sha text;
BEGIN
    SELECT b.state, b.canonical_payload_sha256, b.authority_model_definition_id, b.authority_model_definition_sha256
      INTO v_bundle_state, v_bundle_sha, v_bundle_authority_id, v_bundle_authority_sha
      FROM working_paper_sync_definition_bundle b WHERE b.id = NEW.definition_bundle_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'representation % 引用不存在的 definition bundle %', NEW.id, NEW.definition_bundle_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_bundle_state <> 'approved' THEN
        RAISE EXCEPTION 'representation % 只能由 approved bundle finalize，bundle % 实为 %', NEW.id, NEW.definition_bundle_id, v_bundle_state
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_bundle_sha <> NEW.definition_bundle_sha256 THEN
        RAISE EXCEPTION 'representation % 的 definition_bundle_sha256 与 bundle canonical digest 不一致', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_bundle_authority_id <> NEW.authority_model_definition_id
       OR v_bundle_authority_sha <> NEW.authority_model_definition_sha256 THEN
        RAISE EXCEPTION 'representation % 的 authority model 与 bundle child 未双向锁死', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT a.kind, a.state, a.sha256 INTO v_artifact_kind, v_artifact_state, v_artifact_sha
      FROM working_paper_artifact a WHERE a.id = NEW.artifact_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'representation % 引用不存在的 artifact %', NEW.id, NEW.artifact_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_artifact_kind NOT IN ('canonical', 'projection') THEN
        RAISE EXCEPTION 'representation % 的 artifact kind 必须为 canonical/projection（禁止 incoming/upgrade_candidate/definition），实得 %', NEW.id, v_artifact_kind
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_artifact_state NOT IN ('staged', 'published') THEN
        RAISE EXCEPTION 'representation % 的 artifact state 必须为 staged/published，实得 %', NEW.id, v_artifact_state
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_artifact_sha <> NEW.artifact_sha256 THEN
        RAISE EXCEPTION 'representation % 的 artifact_sha256 与 artifact 实际 digest 不一致', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpcr_identity
    BEFORE INSERT OR UPDATE ON working_paper_content_representation
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_representation_identity();

CREATE OR REPLACE FUNCTION wpsync_check_representation_immutable() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION 'working_paper_content_representation 为 immutable 行，禁止 UPDATE（升级只能新增 generation） (id=%)', OLD.id
        USING ERRCODE = 'check_violation';
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpcr_immutable
    BEFORE UPDATE ON working_paper_content_representation
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_representation_immutable();

-- ═══════════════════════════════════════════════════════════════════════════
-- 8. working_paper_sync_entry_state（design §同名节）
--    current pointer 必须指向 artifact 已 published 的 representation；candidate 不可引用。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_sync_entry_state (
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    entry_id VARCHAR(200) NOT NULL,
    current_representation_id UUID NOT NULL
        REFERENCES working_paper_content_representation(id) ON DELETE RESTRICT,
    representation_generation BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_wpses PRIMARY KEY (wp_id, entry_id),
    CONSTRAINT ck_wpses_generation_positive CHECK (representation_generation >= 1)
);

COMMENT ON TABLE working_paper_sync_entry_state IS
    'V151 entry 级 current representation pointer；只能指向 artifact=published 的 representation，candidate/incoming 一律拒绝（Property 5）';

CREATE OR REPLACE FUNCTION wpsync_check_entry_state_pointer() RETURNS trigger AS $fn$
DECLARE
    v_rep_wp uuid;
    v_rep_entry text;
    v_rep_generation bigint;
    v_artifact_kind text;
    v_artifact_state text;
BEGIN
    SELECT r.wp_id, r.entry_id, r.generation, a.kind, a.state
      INTO v_rep_wp, v_rep_entry, v_rep_generation, v_artifact_kind, v_artifact_state
      FROM working_paper_content_representation r
      JOIN working_paper_artifact a ON a.id = r.artifact_id
     WHERE r.id = NEW.current_representation_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'entry_state(%,%) 指向不存在的 representation %', NEW.wp_id, NEW.entry_id, NEW.current_representation_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_rep_wp <> NEW.wp_id OR v_rep_entry <> NEW.entry_id THEN
        RAISE EXCEPTION 'entry_state(%,%) 指向跨 scope representation(%,%)', NEW.wp_id, NEW.entry_id, v_rep_wp, v_rep_entry
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_rep_generation <> NEW.representation_generation THEN
        RAISE EXCEPTION 'entry_state(%,%) 的 representation_generation % 与 representation 实际 generation % 不一致',
            NEW.wp_id, NEW.entry_id, NEW.representation_generation, v_rep_generation
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_artifact_state <> 'published' THEN
        RAISE EXCEPTION 'entry current pointer 必须指向 published artifact（禁止 staged/candidate/incoming/orphan），实得 %', v_artifact_state
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_artifact_kind NOT IN ('canonical', 'projection') THEN
        RAISE EXCEPTION 'entry current pointer 的 artifact kind 必须为 canonical/projection，实得 %', v_artifact_kind
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpses_pointer
    BEFORE INSERT OR UPDATE ON working_paper_sync_entry_state
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_entry_state_pointer();

-- ═══════════════════════════════════════════════════════════════════════════
-- 9. working_paper_representation_upgrade_candidate（design §同名节 / Requirement 3.4）
--    candidate 不是 representation：finalize 前不可 current、不可被 resolver/room/evidence 使用。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_representation_upgrade_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    content_version_id UUID NOT NULL REFERENCES working_paper_content_version(id) ON DELETE RESTRICT,
    entry_id VARCHAR(200) NOT NULL,
    source_representation_id UUID NOT NULL
        REFERENCES working_paper_content_representation(id) ON DELETE RESTRICT,
    staged_artifact_id UUID NOT NULL REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    staged_artifact_sha256 CHAR(64) NOT NULL,
    template_definition_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_artifact(id) ON DELETE RESTRICT,
    instrumentation_definition_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_artifact(id) ON DELETE RESTRICT,
    target_contract_definition_id UUID
        REFERENCES working_paper_sync_definition_artifact(id) ON DELETE RESTRICT,
    target_definition_bundle_id UUID
        REFERENCES working_paper_sync_definition_bundle(id) ON DELETE RESTRICT,
    finalized_representation_id UUID
        REFERENCES working_paper_content_representation(id) ON DELETE RESTRICT,
    state VARCHAR(30) NOT NULL DEFAULT 'staged',
    visible_equivalence_report_sha256 CHAR(64),
    rollback_source_sha256 CHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalized_at TIMESTAMPTZ,
    CONSTRAINT ck_wpruc_state CHECK (state IN (
        'staged', 'awaiting_contract', 'ready', 'finalized', 'rejected', 'orphaned')),
    CONSTRAINT ck_wpruc_staged_digest CHECK (wpsync_is_digest(staged_artifact_sha256)),
    CONSTRAINT ck_wpruc_equivalence_digest CHECK (
        visible_equivalence_report_sha256 IS NULL OR wpsync_is_digest(visible_equivalence_report_sha256)),
    CONSTRAINT ck_wpruc_rollback_digest CHECK (
        rollback_source_sha256 IS NULL OR wpsync_is_digest(rollback_source_sha256)),
    -- ready/finalized 前必须补齐 approved contract + bundle（可空只表示尚未批准，不是 canonical null marker）
    CONSTRAINT ck_wpruc_ready_requires_bundle CHECK (
        state NOT IN ('ready', 'finalized')
        OR (target_contract_definition_id IS NOT NULL AND target_definition_bundle_id IS NOT NULL)),
    CONSTRAINT ck_wpruc_finalized_pointer CHECK (
        (state = 'finalized') = (finalized_representation_id IS NOT NULL)),
    CONSTRAINT ck_wpruc_finalized_at CHECK ((state = 'finalized') = (finalized_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_wpruc_entry ON working_paper_representation_upgrade_candidate (wp_id, entry_id, state);

COMMENT ON TABLE working_paper_representation_upgrade_candidate IS
    'V151 representation 升级候选：staged 但 non-current；只能引用已校验 staged artifact，finalize 需 approved contract+bundle，且永不进入 resolver/room/current/evidence（Property 5 / Requirement 3.4）';

-- candidate 只能引用 upgrade_candidate 类 staged artifact；finalize 需 approved bundle 且不得推进 content revision
CREATE OR REPLACE FUNCTION wpsync_check_upgrade_candidate() RETURNS trigger AS $fn$
DECLARE
    v_artifact_kind text;
    v_artifact_state text;
    v_artifact_sha text;
    v_bundle_state text;
    v_contract_state text;
    v_fin_version uuid;
BEGIN
    SELECT a.kind, a.state, a.sha256 INTO v_artifact_kind, v_artifact_state, v_artifact_sha
      FROM working_paper_artifact a WHERE a.id = NEW.staged_artifact_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'candidate % 引用不存在的 staged artifact %', NEW.id, NEW.staged_artifact_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_artifact_kind <> 'upgrade_candidate' THEN
        RAISE EXCEPTION 'candidate % 的 artifact kind 必须为 upgrade_candidate，实得 %', NEW.id, v_artifact_kind
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_artifact_state NOT IN ('staged', 'candidate') THEN
        RAISE EXCEPTION 'candidate % 的 artifact 只能 staged/candidate（永不 published/durable），实得 %', NEW.id, v_artifact_state
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_artifact_sha <> NEW.staged_artifact_sha256 THEN
        RAISE EXCEPTION 'candidate % 的 staged_artifact_sha256 与 artifact 实际 digest 不一致', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.state IN ('ready', 'finalized') THEN
        SELECT b.state INTO v_bundle_state FROM working_paper_sync_definition_bundle b
         WHERE b.id = NEW.target_definition_bundle_id;
        IF v_bundle_state IS DISTINCT FROM 'approved' THEN
            RAISE EXCEPTION 'candidate % 进入 %/finalized 前 target bundle 必须 approved，实得 %', NEW.id, NEW.state, coalesce(v_bundle_state, 'MISSING')
                USING ERRCODE = 'check_violation';
        END IF;
        SELECT d.state INTO v_contract_state FROM working_paper_sync_definition_artifact d
         WHERE d.id = NEW.target_contract_definition_id AND d.kind = 'contract';
        IF v_contract_state IS DISTINCT FROM 'approved' THEN
            RAISE EXCEPTION 'candidate % 的 per-entry contract 必须为 approved contract definition，实得 %', NEW.id, coalesce(v_contract_state, 'MISSING')
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    -- finalize 只为**同一** content version 创建新 representation generation（不得推进 content revision）
    IF NEW.finalized_representation_id IS NOT NULL THEN
        SELECT r.content_version_id INTO v_fin_version
          FROM working_paper_content_representation r WHERE r.id = NEW.finalized_representation_id;
        IF v_fin_version IS DISTINCT FROM NEW.content_version_id THEN
            RAISE EXCEPTION 'candidate % finalize 出的 representation 必须绑定同一 content version（禁止推进 content revision）', NEW.id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpruc_guard
    BEFORE INSERT OR UPDATE ON working_paper_representation_upgrade_candidate
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_upgrade_candidate();

-- ═══════════════════════════════════════════════════════════════════════════
-- 10. working_paper_pending_mutation（design §同名节 / Requirement 3.1）
--     作用域绑定 + 短 TTL + 单次逻辑消费 + 幂等重放。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_pending_mutation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    entry_id VARCHAR(200) NOT NULL,
    sheet_key VARCHAR(200) NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    expected_revision BIGINT NOT NULL,
    payload_artifact_id UUID NOT NULL REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    payload_sha256 CHAR(64) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'pending',
    result_operation_id UUID,
    result_content_version_id UUID REFERENCES working_paper_content_version(id) ON DELETE RESTRICT,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    committed_at TIMESTAMPTZ,
    CONSTRAINT uq_wppm_idempotency UNIQUE (wp_id, entry_id, user_id, idempotency_key),
    CONSTRAINT ck_wppm_state CHECK (state IN ('pending', 'committing', 'committed', 'expired', 'invalidated')),
    CONSTRAINT ck_wppm_payload_digest CHECK (wpsync_is_digest(payload_sha256)),
    CONSTRAINT ck_wppm_expected_revision CHECK (expected_revision >= 0),
    -- committed 必须同时留下可重放结果（否则重放会二次提交）
    CONSTRAINT ck_wppm_committed_result CHECK (
        state <> 'committed'
        OR (result_operation_id IS NOT NULL AND result_content_version_id IS NOT NULL AND committed_at IS NOT NULL)),
    -- 未 committed 不得预留结果
    CONSTRAINT ck_wppm_uncommitted_no_result CHECK (
        state = 'committed'
        OR (result_operation_id IS NULL AND result_content_version_id IS NULL AND committed_at IS NULL)),
    -- 短 TTL：expires_at 必须晚于 created_at
    CONSTRAINT ck_wppm_ttl CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_wppm_scope ON working_paper_pending_mutation (project_id, wp_id, entry_id, state);
CREATE INDEX IF NOT EXISTS idx_wppm_expiry ON working_paper_pending_mutation (expires_at) WHERE state IN ('pending', 'committing');

COMMENT ON TABLE working_paper_pending_mutation IS
    'V151 pending mutation：flushHtml 只创建它、不推进 revision；作用域/payload digest/expected revision/TTL 任一不符即拒绝，committed 后同 token 重放返回既有 operation/version（Property 10）';

-- ═══════════════════════════════════════════════════════════════════════════
-- 11. working_paper_sync_scope_index（design §同名节）
--     authorization-only 归属索引：只存非敏感 project/wp/entry + 对象类别 + opaque 对象 id。
--     禁止 payload/业务状态/hash/错误/候选摘要/authorization result。
--     tombstone 永不物理删除或清空，resource id 永不复用。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_sync_scope_index (
    resource_kind VARCHAR(40) NOT NULL,
    resource_id TEXT NOT NULL,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    entry_id VARCHAR(200) NOT NULL,
    room_id UUID,
    generation INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    retired_at TIMESTAMPTZ,
    CONSTRAINT pk_wpssi PRIMARY KEY (resource_kind, resource_id),
    CONSTRAINT ck_wpssi_resource_kind CHECK (resource_kind IN (
        'room', 'participant', 'client_confirmation', 'forcesave_request', 'close_intent',
        'callback_delivery', 'content_application', 'sync_operation', 'recovery_case',
        'sync_conflict', 'content_version', 'content_representation', 'upgrade_candidate',
        'pending_mutation', 'sync_test_run', 'evidence_scenario')),
    -- opaque identity：纯数字（numeric revision）禁作 scope/resource/route key
    CONSTRAINT ck_wpssi_opaque_resource_id CHECK (wpsync_is_opaque_resource_id(resource_id)),
    -- content version 的 resource_id 只能是 immutable UUID version_id
    CONSTRAINT ck_wpssi_content_version_uuid CHECK (
        resource_kind <> 'content_version' OR wpsync_is_uuid_text(resource_id)),
    CONSTRAINT ck_wpssi_entry_non_empty CHECK (length(btrim(entry_id)) > 0),
    CONSTRAINT ck_wpssi_generation_positive CHECK (generation IS NULL OR generation >= 1)
);

CREATE INDEX IF NOT EXISTS idx_wpssi_scope ON working_paper_sync_scope_index (project_id, wp_id, entry_id);
CREATE INDEX IF NOT EXISTS idx_wpssi_room ON working_paper_sync_scope_index (room_id, generation);

COMMENT ON TABLE working_paper_sync_scope_index IS
    'V151 authorization-only 归属索引：guard 在读任何业务 row 前只能读它；禁存 payload/状态/hash/错误/authorization result；tombstone（retired_at）永不物理删除、永不清空、resource id 永不复用';

-- 物理删除禁令（tombstone 永久保留以防 id 复用）
CREATE OR REPLACE FUNCTION wpsync_forbid_scope_index_delete() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION 'working_paper_sync_scope_index 禁止物理删除（退役只能设置 retired_at）: %/%', OLD.resource_kind, OLD.resource_id
        USING ERRCODE = 'check_violation';
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpssi_no_delete
    BEFORE DELETE ON working_paper_sync_scope_index
    FOR EACH ROW EXECUTE FUNCTION wpsync_forbid_scope_index_delete();

-- scope 不可变 + tombstone 不可清空
CREATE OR REPLACE FUNCTION wpsync_check_scope_index_update() RETURNS trigger AS $fn$
BEGIN
    IF NEW.resource_kind IS DISTINCT FROM OLD.resource_kind
       OR NEW.resource_id IS DISTINCT FROM OLD.resource_id
       OR NEW.project_id IS DISTINCT FROM OLD.project_id
       OR NEW.wp_id IS DISTINCT FROM OLD.wp_id
       OR NEW.entry_id IS DISTINCT FROM OLD.entry_id
       OR NEW.room_id IS DISTINCT FROM OLD.room_id
       OR NEW.generation IS DISTINCT FROM OLD.generation THEN
        RAISE EXCEPTION 'scope index 的 scope（kind/id/project/wp/entry/room/generation）不可变，禁止跨 scope 重绑或 id 复用: %/%', OLD.resource_kind, OLD.resource_id
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.retired_at IS NOT NULL AND NEW.retired_at IS NULL THEN
        RAISE EXCEPTION 'scope index tombstone 不可清空（retired_at 一经设置不得回到 NULL）: %/%', OLD.resource_kind, OLD.resource_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpssi_update_guard
    BEFORE UPDATE ON working_paper_sync_scope_index
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_scope_index_update();

-- ═══════════════════════════════════════════════════════════════════════════
-- 12. working_paper_oo_room（design §同名节 / Requirement 2.5 / 4.11）
--     server last-applied 与 client-confirmed base 是两套独立指针（Property 62）。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_oo_room (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    entry_id VARCHAR(200) NOT NULL,
    doc_key VARCHAR(150) NOT NULL,
    generation INTEGER NOT NULL,
    opened_base_version_id UUID NOT NULL
        REFERENCES working_paper_content_version(id) ON DELETE RESTRICT,
    last_applied_version_id UUID REFERENCES working_paper_content_version(id) ON DELETE RESTRICT,
    client_confirmed_base_version_id UUID REFERENCES working_paper_content_version(id) ON DELETE RESTRICT,
    client_confirmed_representation_id UUID
        REFERENCES working_paper_content_representation(id) ON DELETE RESTRICT,
    client_confirmed_definition_bundle_id UUID
        REFERENCES working_paper_sync_definition_bundle(id) ON DELETE RESTRICT,
    client_confirmed_definition_bundle_sha256 CHAR(64),
    client_confirmed_projection_sha256 CHAR(64),
    latest_request_sequence BIGINT NOT NULL DEFAULT 0,
    latest_durable_sequence BIGINT NOT NULL DEFAULT 0,
    latest_durable_application_id UUID,
    write_fence_epoch BIGINT NOT NULL DEFAULT 1,
    close_barrier_epoch BIGINT NOT NULL DEFAULT 0,
    close_leader_intent_id UUID,
    close_leader_eligibility_epoch BIGINT NOT NULL DEFAULT 0,
    close_leader_eligibility_digest CHAR(64),
    state VARCHAR(30) NOT NULL DEFAULT 'opening',
    refresh_required_at TIMESTAMPTZ,
    refresh_reason VARCHAR(60),
    expires_at TIMESTAMPTZ NOT NULL,
    superseded_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpoor_doc_key UNIQUE (doc_key),
    CONSTRAINT uq_wpoor_generation UNIQUE (wp_id, entry_id, generation),
    CONSTRAINT ck_wpoor_generation_positive CHECK (generation >= 1),
    CONSTRAINT ck_wpoor_state CHECK (state IN (
        'opening', 'active', 'close_barrier', 'closing', 'refresh_required',
        'superseded', 'closed', 'recovery_required')),
    CONSTRAINT ck_wpoor_sequences_non_negative CHECK (
        latest_request_sequence >= 0 AND latest_durable_sequence >= 0
        AND write_fence_epoch >= 1 AND close_barrier_epoch >= 0 AND close_leader_eligibility_epoch >= 0),
    -- durable fence 不得超过已发出的 request fence
    CONSTRAINT ck_wpoor_durable_le_request CHECK (latest_durable_sequence <= latest_request_sequence),
    CONSTRAINT ck_wpoor_client_bundle_digest CHECK (
        client_confirmed_definition_bundle_sha256 IS NULL
        OR wpsync_is_digest(client_confirmed_definition_bundle_sha256)),
    CONSTRAINT ck_wpoor_client_projection_digest CHECK (
        client_confirmed_projection_sha256 IS NULL OR wpsync_is_digest(client_confirmed_projection_sha256)),
    CONSTRAINT ck_wpoor_eligibility_digest CHECK (
        close_leader_eligibility_digest IS NULL OR wpsync_is_digest(close_leader_eligibility_digest)),
    -- client-confirmed 是一个整体快照：bundle id/digest 与 representation/base 必须同时具备
    CONSTRAINT ck_wpoor_client_confirmed_group CHECK (
        (client_confirmed_base_version_id IS NULL
         AND client_confirmed_representation_id IS NULL
         AND client_confirmed_definition_bundle_id IS NULL
         AND client_confirmed_definition_bundle_sha256 IS NULL
         AND client_confirmed_projection_sha256 IS NULL)
        OR (client_confirmed_base_version_id IS NOT NULL
         AND client_confirmed_representation_id IS NOT NULL
         AND client_confirmed_definition_bundle_id IS NOT NULL
         AND client_confirmed_definition_bundle_sha256 IS NOT NULL
         AND client_confirmed_projection_sha256 IS NOT NULL)),
    -- refresh_required 必须留下原因与时间（不得静默 refresh）
    CONSTRAINT ck_wpoor_refresh_reason CHECK (
        state <> 'refresh_required' OR (refresh_required_at IS NOT NULL AND refresh_reason IS NOT NULL)),
    -- durable fence 与 canonical application 成对
    CONSTRAINT ck_wpoor_durable_fence_pair CHECK (
        (latest_durable_application_id IS NULL AND latest_durable_sequence = 0)
        OR latest_durable_application_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_wpoor_scope ON working_paper_oo_room (project_id, wp_id, entry_id);
CREATE INDEX IF NOT EXISTS idx_wpoor_state ON working_paper_oo_room (state, expires_at);

COMMENT ON TABLE working_paper_oo_room IS
    'V151 shared OO room：last_applied_version_id（服务器已应用）与 client_confirmed_*（编辑器实际持有）是两套独立指针，禁止用单一 last_ack 混同；room 不保存单一 user_id/mode/permission_epoch（Requirement 2.5 / Property 62）';
COMMENT ON COLUMN working_paper_oo_room.latest_durable_application_id IS
    'canonical application fence：与 latest_durable_sequence 原子更新；resolve 先比 canonical application 再比 effective sequence（FK 见 fk_wpoor_latest_durable_application，application 表建成后追加）';

-- room 单调 fence：request/durable sequence、write fence、barrier/eligibility epoch 只增不减
CREATE OR REPLACE FUNCTION wpsync_check_room_monotonic() RETURNS trigger AS $fn$
BEGIN
    IF NEW.wp_id IS DISTINCT FROM OLD.wp_id
       OR NEW.entry_id IS DISTINCT FROM OLD.entry_id
       OR NEW.generation IS DISTINCT FROM OLD.generation
       OR NEW.doc_key IS DISTINCT FROM OLD.doc_key
       OR NEW.opened_base_version_id IS DISTINCT FROM OLD.opened_base_version_id THEN
        RAISE EXCEPTION 'room 身份列（wp/entry/generation/doc_key/opened_base）不可变 (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.latest_request_sequence < OLD.latest_request_sequence
       OR NEW.latest_durable_sequence < OLD.latest_durable_sequence
       OR NEW.write_fence_epoch < OLD.write_fence_epoch
       OR NEW.close_barrier_epoch < OLD.close_barrier_epoch
       OR NEW.close_leader_eligibility_epoch < OLD.close_leader_eligibility_epoch THEN
        RAISE EXCEPTION 'room fence 只可单调提升（request=%→%, durable=%→%, write_fence=%→%, barrier=%→%, eligibility=%→%）',
            OLD.latest_request_sequence, NEW.latest_request_sequence,
            OLD.latest_durable_sequence, NEW.latest_durable_sequence,
            OLD.write_fence_epoch, NEW.write_fence_epoch,
            OLD.close_barrier_epoch, NEW.close_barrier_epoch,
            OLD.close_leader_eligibility_epoch, NEW.close_leader_eligibility_epoch
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpoor_monotonic
    BEFORE UPDATE ON working_paper_oo_room
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_room_monotonic();

-- ═══════════════════════════════════════════════════════════════════════════
-- 13. working_paper_oo_participant（design §同名节 / Requirement 2.6）
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_oo_participant (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES working_paper_oo_room(id) ON DELETE RESTRICT,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    mode VARCHAR(10) NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'active',
    permission_epoch BIGINT NOT NULL,
    joined_write_fence_epoch BIGINT NOT NULL,
    lease_token_hash CHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    left_at TIMESTAMPTZ,
    oo_drop_confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_wpoop_mode CHECK (mode IN ('edit', 'view')),
    -- `closing` 是 close intent 创建时的原子中间态，不再计入 active confirmed editor 集合
    CONSTRAINT ck_wpoop_state CHECK (state IN ('active', 'closing', 'left', 'revoked', 'expired')),
    CONSTRAINT ck_wpoop_lease_hash CHECK (wpsync_is_digest(lease_token_hash)),
    CONSTRAINT ck_wpoop_epochs CHECK (permission_epoch >= 0 AND joined_write_fence_epoch >= 1),
    CONSTRAINT ck_wpoop_revoked_at CHECK (state <> 'revoked' OR revoked_at IS NOT NULL),
    CONSTRAINT ck_wpoop_left_at CHECK (state <> 'left' OR left_at IS NOT NULL)
);

-- 同 room 同 user 只能有一个未终结 lease（active/closing）
CREATE UNIQUE INDEX IF NOT EXISTS uq_wpoop_active_lease
    ON working_paper_oo_participant (room_id, user_id)
    WHERE state IN ('active', 'closing');

CREATE INDEX IF NOT EXISTS idx_wpoop_room_state ON working_paper_oo_participant (room_id, state);

COMMENT ON TABLE working_paper_oo_participant IS
    'V151 per-user lease：逐人 permission_epoch/mode/state/TTL；close intent 创建时在 room lock 内 active→closing，closing 不再计入 active confirmed editor 仲裁集合（Requirement 2.6）';

-- ═══════════════════════════════════════════════════════════════════════════
-- 14. working_paper_oo_client_confirmation（design §同名节 / Requirement 3.7 / Property 11）
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_oo_client_confirmation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES working_paper_oo_room(id) ON DELETE RESTRICT,
    participant_id UUID NOT NULL REFERENCES working_paper_oo_participant(id) ON DELETE RESTRICT,
    generation INTEGER NOT NULL,
    doc_key VARCHAR(150) NOT NULL,
    representation_id UUID NOT NULL
        REFERENCES working_paper_content_representation(id) ON DELETE RESTRICT,
    artifact_sha256 CHAR(64) NOT NULL,
    content_version_id UUID NOT NULL REFERENCES working_paper_content_version(id) ON DELETE RESTRICT,
    projection_sha256 CHAR(64) NOT NULL,
    definition_bundle_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_bundle(id) ON DELETE RESTRICT,
    definition_bundle_sha256 CHAR(64) NOT NULL,
    authority_model_definition_sha256 CHAR(64) NOT NULL,
    bundle_slots_digest CHAR(64) NOT NULL,
    write_fence_epoch BIGINT NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    invalidated_at TIMESTAMPTZ,
    CONSTRAINT ck_wpocc_generation_positive CHECK (generation >= 1),
    CONSTRAINT ck_wpocc_artifact_digest CHECK (wpsync_is_digest(artifact_sha256)),
    CONSTRAINT ck_wpocc_projection_digest CHECK (wpsync_is_digest(projection_sha256)),
    CONSTRAINT ck_wpocc_bundle_digest CHECK (wpsync_is_digest(definition_bundle_sha256)),
    CONSTRAINT ck_wpocc_authority_digest CHECK (wpsync_is_digest(authority_model_definition_sha256)),
    CONSTRAINT ck_wpocc_slots_digest CHECK (wpsync_is_digest(bundle_slots_digest)),
    CONSTRAINT ck_wpocc_fence CHECK (write_fence_epoch >= 1),
    CONSTRAINT uq_wpocc_idempotency UNIQUE (room_id, participant_id, generation, idempotency_key)
);

-- 同 (room, participant, generation) 只能有一个 active confirmation
CREATE UNIQUE INDEX IF NOT EXISTS uq_wpocc_active
    ON working_paper_oo_client_confirmation (room_id, participant_id, generation)
    WHERE invalidated_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_wpocc_room_generation ON working_paper_oo_client_confirmation (room_id, generation);

COMMENT ON TABLE working_paper_oo_client_confirmation IS
    'V151 descriptor confirmation：onDocumentReady 后逐项回传 room/generation/doc_key/representation/artifact/approved bundle/authority model/fence；重复 key 返回同 confirmation，陈旧 identity 由 service 返 409（Property 11）';

-- confirmation 的 representation/bundle 必须一致，且 representation 必须属同一 content version
CREATE OR REPLACE FUNCTION wpsync_check_client_confirmation() RETURNS trigger AS $fn$
DECLARE
    v_rep_version uuid;
    v_rep_bundle uuid;
    v_rep_bundle_sha text;
    v_rep_authority_sha text;
    v_rep_artifact_sha text;
    v_room_generation integer;
    v_room_doc_key text;
BEGIN
    SELECT r.content_version_id, r.definition_bundle_id, r.definition_bundle_sha256,
           r.authority_model_definition_sha256, r.artifact_sha256
      INTO v_rep_version, v_rep_bundle, v_rep_bundle_sha, v_rep_authority_sha, v_rep_artifact_sha
      FROM working_paper_content_representation r WHERE r.id = NEW.representation_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'confirmation % 引用不存在的 representation %（candidate 不是 representation）', NEW.id, NEW.representation_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_rep_version <> NEW.content_version_id THEN
        RAISE EXCEPTION 'confirmation % 的 content_version_id 与 representation 实际 content version 不一致', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_rep_bundle <> NEW.definition_bundle_id
       OR v_rep_bundle_sha <> NEW.definition_bundle_sha256
       OR v_rep_authority_sha <> NEW.authority_model_definition_sha256 THEN
        RAISE EXCEPTION 'confirmation % 的 bundle/authority identity 与 representation 未双向锁死', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_rep_artifact_sha <> NEW.artifact_sha256 THEN
        RAISE EXCEPTION 'confirmation % 的 artifact_sha256 与 representation 不一致', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT m.generation, m.doc_key INTO v_room_generation, v_room_doc_key
      FROM working_paper_oo_room m WHERE m.id = NEW.room_id;
    IF v_room_generation <> NEW.generation OR v_room_doc_key <> NEW.doc_key THEN
        RAISE EXCEPTION 'confirmation % 的 generation/doc_key 与 room 不一致（陈旧 descriptor 必须拒绝）', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpocc_identity
    BEFORE INSERT OR UPDATE ON working_paper_oo_client_confirmation
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_client_confirmation();

-- ═══════════════════════════════════════════════════════════════════════════
-- 15. working_paper_forcesave_request（design §同名节 / Requirement 4.1）
--     复合幂等键 (room,generation,initiator,kind,idempotency_key) + frozen fingerprint。
--     close_capture 以 generation 内 open-state partial unique 保证 at-most-one。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_forcesave_request (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES working_paper_oo_room(id) ON DELETE RESTRICT,
    generation INTEGER NOT NULL,
    request_sequence BIGINT NOT NULL,
    kind VARCHAR(20) NOT NULL,
    initiated_by_participant_id UUID NOT NULL
        REFERENCES working_paper_oo_participant(id) ON DELETE RESTRICT,
    initiator_permission_epoch BIGINT NOT NULL,
    client_edit_epoch BIGINT NOT NULL,
    write_fence_epoch BIGINT NOT NULL,
    client_base_version_id UUID NOT NULL REFERENCES working_paper_content_version(id) ON DELETE RESTRICT,
    client_base_representation_id UUID NOT NULL
        REFERENCES working_paper_content_representation(id) ON DELETE RESTRICT,
    client_base_projection_sha256 CHAR(64) NOT NULL,
    definition_bundle_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_bundle(id) ON DELETE RESTRICT,
    definition_bundle_sha256 CHAR(64) NOT NULL,
    authority_model_definition_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_artifact(id) ON DELETE RESTRICT,
    authority_model_definition_sha256 CHAR(64) NOT NULL,
    adapter_build_digest CHAR(64) NOT NULL,
    contributor_snapshot_digest CHAR(64) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    frozen_request_fingerprint CHAR(64) NOT NULL,
    state VARCHAR(30) NOT NULL DEFAULT 'frozen',
    accepted_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpfr_sequence UNIQUE (room_id, generation, request_sequence),
    -- 复合幂等键：跨 participant/kind 复用同 key 不得命中旧 request
    CONSTRAINT uq_wpfr_idempotency UNIQUE (room_id, generation, initiated_by_participant_id, kind, idempotency_key),
    CONSTRAINT ck_wpfr_kind CHECK (kind IN ('forcesave', 'close_capture', 'recovery_claim')),
    CONSTRAINT ck_wpfr_state CHECK (state IN (
        'frozen', 'pending', 'accepted', 'correlated', 'terminal',
        'rejected', 'unmatched', 'superseded', 'authorization_stale')),
    CONSTRAINT ck_wpfr_generation_positive CHECK (generation >= 1),
    CONSTRAINT ck_wpfr_sequence_positive CHECK (request_sequence >= 1),
    CONSTRAINT ck_wpfr_epochs CHECK (
        initiator_permission_epoch >= 0 AND client_edit_epoch >= 0 AND write_fence_epoch >= 1),
    CONSTRAINT ck_wpfr_base_projection_digest CHECK (wpsync_is_digest(client_base_projection_sha256)),
    CONSTRAINT ck_wpfr_bundle_digest CHECK (wpsync_is_digest(definition_bundle_sha256)),
    CONSTRAINT ck_wpfr_authority_digest CHECK (wpsync_is_digest(authority_model_definition_sha256)),
    CONSTRAINT ck_wpfr_adapter_digest CHECK (wpsync_is_digest(adapter_build_digest)),
    CONSTRAINT ck_wpfr_contributor_digest CHECK (wpsync_is_digest(contributor_snapshot_digest)),
    CONSTRAINT ck_wpfr_fingerprint CHECK (wpsync_is_digest(frozen_request_fingerprint))
);

-- close_capture 在 generation 内 at-most-one open（exactly-one 由行为测试证明）
CREATE UNIQUE INDEX IF NOT EXISTS uq_wpfr_open_close_capture
    ON working_paper_forcesave_request (room_id, generation)
    WHERE kind = 'close_capture' AND state IN ('frozen', 'pending', 'accepted', 'correlated');

CREATE INDEX IF NOT EXISTS idx_wpfr_room_state ON working_paper_forcesave_request (room_id, generation, state);

COMMENT ON TABLE working_paper_forcesave_request IS
    'V151 frozen forcesave/close-capture/recovery-claim request：Command Service 前同事务冻结 base/representation/approved bundle/authority model/fence/contributors 并算 frozen_request_fingerprint；recovery_claim 不调用 Command Service（Requirement 4.1）';
COMMENT ON COLUMN working_paper_forcesave_request.frozen_request_fingerprint IS
    'canonical hash of confirmation/base/representation/bundle/fence/contributors；Idempotency-Key cache hit 必须逐项等值，否则 409 且不得返回旧标识';

-- request 冻结字段不可变（历史 retry 原样使用）
CREATE OR REPLACE FUNCTION wpsync_check_request_frozen() RETURNS trigger AS $fn$
BEGIN
    IF NEW.room_id IS DISTINCT FROM OLD.room_id
       OR NEW.generation IS DISTINCT FROM OLD.generation
       OR NEW.request_sequence IS DISTINCT FROM OLD.request_sequence
       OR NEW.kind IS DISTINCT FROM OLD.kind
       OR NEW.initiated_by_participant_id IS DISTINCT FROM OLD.initiated_by_participant_id
       OR NEW.initiator_permission_epoch IS DISTINCT FROM OLD.initiator_permission_epoch
       OR NEW.client_base_version_id IS DISTINCT FROM OLD.client_base_version_id
       OR NEW.client_base_representation_id IS DISTINCT FROM OLD.client_base_representation_id
       OR NEW.client_base_projection_sha256 IS DISTINCT FROM OLD.client_base_projection_sha256
       OR NEW.definition_bundle_id IS DISTINCT FROM OLD.definition_bundle_id
       OR NEW.definition_bundle_sha256 IS DISTINCT FROM OLD.definition_bundle_sha256
       OR NEW.authority_model_definition_id IS DISTINCT FROM OLD.authority_model_definition_id
       OR NEW.authority_model_definition_sha256 IS DISTINCT FROM OLD.authority_model_definition_sha256
       OR NEW.adapter_build_digest IS DISTINCT FROM OLD.adapter_build_digest
       OR NEW.contributor_snapshot_digest IS DISTINCT FROM OLD.contributor_snapshot_digest
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.frozen_request_fingerprint IS DISTINCT FROM OLD.frozen_request_fingerprint THEN
        RAISE EXCEPTION 'forcesave request 的冻结字段不可变，只允许 state/accepted_at/finished_at 推进 (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpfr_frozen
    BEFORE UPDATE ON working_paper_forcesave_request
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_request_frozen();

-- request 的 bundle/authority 必须与冻结 representation 一致（禁止按 alias 重组）
CREATE OR REPLACE FUNCTION wpsync_check_request_identity() RETURNS trigger AS $fn$
DECLARE
    v_rep_bundle uuid;
    v_rep_bundle_sha text;
    v_rep_authority_id uuid;
    v_rep_authority_sha text;
BEGIN
    SELECT r.definition_bundle_id, r.definition_bundle_sha256,
           r.authority_model_definition_id, r.authority_model_definition_sha256
      INTO v_rep_bundle, v_rep_bundle_sha, v_rep_authority_id, v_rep_authority_sha
      FROM working_paper_content_representation r WHERE r.id = NEW.client_base_representation_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'request % 引用不存在的 client base representation %', NEW.id, NEW.client_base_representation_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_rep_bundle <> NEW.definition_bundle_id
       OR v_rep_bundle_sha <> NEW.definition_bundle_sha256
       OR v_rep_authority_id <> NEW.authority_model_definition_id
       OR v_rep_authority_sha <> NEW.authority_model_definition_sha256 THEN
        RAISE EXCEPTION 'request % 冻结的 bundle/authority identity 与 client base representation 不一致', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpfr_identity
    BEFORE INSERT ON working_paper_forcesave_request
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_request_identity();

-- ═══════════════════════════════════════════════════════════════════════════
-- 16. working_paper_oo_close_intent + append-only event（design §同名节 / Requirement 4.10）
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_oo_close_intent (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES working_paper_oo_room(id) ON DELETE RESTRICT,
    generation INTEGER NOT NULL,
    participant_id UUID NOT NULL REFERENCES working_paper_oo_participant(id) ON DELETE RESTRICT,
    client_confirmation_id UUID NOT NULL
        REFERENCES working_paper_oo_client_confirmation(id) ON DELETE RESTRICT,
    intent_sequence BIGINT NOT NULL,
    barrier_epoch BIGINT NOT NULL,
    eligibility_epoch BIGINT NOT NULL DEFAULT 0,
    ordinary_forcesave_request_id UUID
        REFERENCES working_paper_forcesave_request(id) ON DELETE RESTRICT,
    promoted_request_id UUID REFERENCES working_paper_forcesave_request(id) ON DELETE RESTRICT,
    state VARCHAR(30) NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reconciled_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    CONSTRAINT uq_wpoci_sequence UNIQUE (room_id, generation, intent_sequence),
    CONSTRAINT ck_wpoci_state CHECK (state IN (
        'created', 'ordinary_forcesaving', 'waiting_barrier', 'leader_ready', 'promoted',
        'retryable_blocked', 'authorization_stale', 'successor_selected',
        'recovery_required', 'superseded', 'error')),
    CONSTRAINT ck_wpoci_generation_positive CHECK (generation >= 1),
    CONSTRAINT ck_wpoci_sequence_positive CHECK (intent_sequence >= 1),
    CONSTRAINT ck_wpoci_epochs CHECK (barrier_epoch >= 0 AND eligibility_epoch >= 0),
    -- promoted 必须且只能在 promoted 状态携带 close_capture request
    CONSTRAINT ck_wpoci_promoted_pair CHECK ((state = 'promoted') = (promoted_request_id IS NOT NULL))
);

-- 同 (room, generation, participant) 只能有一个未终结 intent
CREATE UNIQUE INDEX IF NOT EXISTS uq_wpoci_active
    ON working_paper_oo_close_intent (room_id, generation, participant_id)
    WHERE state NOT IN ('superseded', 'error', 'recovery_required', 'promoted');

CREATE INDEX IF NOT EXISTS idx_wpoci_room ON working_paper_oo_close_intent (room_id, generation, state);

COMMENT ON TABLE working_paper_oo_close_intent IS
    'V151 clean-close intent：创建即 participant active→closing 并推进 room barrier；leader 由最高 (intent_sequence,id) + eligibility snapshot 确定，promotion 前失格则写 authorization_stale 并选 successor，无 successor 落 generation supersede + recovery_required 终态（Requirement 4.10）';

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_wpoor_close_leader_intent') THEN
        ALTER TABLE working_paper_oo_room ADD CONSTRAINT fk_wpoor_close_leader_intent
            FOREIGN KEY (close_leader_intent_id)
            REFERENCES working_paper_oo_close_intent(id) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

-- promoted request 必须是同 room/generation 的 close_capture
CREATE OR REPLACE FUNCTION wpsync_check_close_intent_promotion() RETURNS trigger AS $fn$
DECLARE
    v_kind text;
    v_room uuid;
    v_generation integer;
BEGIN
    IF NEW.promoted_request_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT q.kind, q.room_id, q.generation INTO v_kind, v_room, v_generation
      FROM working_paper_forcesave_request q WHERE q.id = NEW.promoted_request_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'close intent % 的 promoted_request_id % 不存在', NEW.id, NEW.promoted_request_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_kind <> 'close_capture' THEN
        RAISE EXCEPTION 'close intent % 只能提升为 close_capture request，实得 kind=%', NEW.id, v_kind
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_room <> NEW.room_id OR v_generation <> NEW.generation THEN
        RAISE EXCEPTION 'close intent % 的 promoted request 跨 room/generation', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpoci_promotion
    BEFORE INSERT OR UPDATE ON working_paper_oo_close_intent
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_close_intent_promotion();

CREATE TABLE IF NOT EXISTS working_paper_oo_close_intent_event (
    id BIGSERIAL PRIMARY KEY,
    intent_id UUID NOT NULL REFERENCES working_paper_oo_close_intent(id) ON DELETE RESTRICT,
    sequence_no INTEGER NOT NULL,
    from_state VARCHAR(30),
    to_state VARCHAR(30) NOT NULL,
    eligibility_epoch BIGINT NOT NULL,
    eligibility_digest CHAR(64),
    actor_type VARCHAR(20) NOT NULL,
    actor_id UUID,
    authorization_result VARCHAR(30),
    error_code VARCHAR(60),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpocie_sequence UNIQUE (intent_id, sequence_no),
    CONSTRAINT ck_wpocie_sequence_positive CHECK (sequence_no >= 1),
    CONSTRAINT ck_wpocie_actor_type CHECK (actor_type IN ('user', 'system', 'callback', 'reconciler')),
    CONSTRAINT ck_wpocie_eligibility_digest CHECK (
        eligibility_digest IS NULL OR wpsync_is_digest(eligibility_digest))
);

CREATE INDEX IF NOT EXISTS idx_wpocie_intent ON working_paper_oo_close_intent_event (intent_id, sequence_no);

COMMENT ON TABLE working_paper_oo_close_intent_event IS
    'V151 close-intent append-only timeline：authorization_stale / successor_selected / recovery_required 等 eligibility 变化各自恰一个递增 event；同 eligibility digest 重放不得产生第二 event（Property 68）';

-- ═══════════════════════════════════════════════════════════════════════════
-- 17. working_paper_callback_recovery_case + 独立 append-only event
--     （design §同名节 / Requirement 5.8 / 13.5）
--     claim 前 request/application/operation 全空；download-only 三者恒空。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_callback_recovery_case (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    entry_id VARCHAR(200) NOT NULL,
    room_id UUID NOT NULL REFERENCES working_paper_oo_room(id) ON DELETE RESTRICT,
    generation INTEGER NOT NULL,
    source_delivery_key CHAR(64) NOT NULL UNIQUE,
    incoming_artifact_id UUID NOT NULL REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    reason VARCHAR(30) NOT NULL,
    candidate_confirmation_digest CHAR(64),
    candidate_contributor_digest CHAR(64),
    state VARCHAR(30) NOT NULL DEFAULT 'unclaimed',
    claimed_by_participant_id UUID REFERENCES working_paper_oo_participant(id) ON DELETE RESTRICT,
    prior_confirmation_id UUID
        REFERENCES working_paper_oo_client_confirmation(id) ON DELETE RESTRICT,
    recovery_request_id UUID REFERENCES working_paper_forcesave_request(id) ON DELETE RESTRICT,
    application_id UUID,
    operation_id UUID,
    claimed_definition_bundle_id UUID
        REFERENCES working_paper_sync_definition_bundle(id) ON DELETE RESTRICT,
    claimed_definition_bundle_sha256 CHAR(64),
    idempotency_key VARCHAR(200),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    CONSTRAINT ck_wpcrc_reason CHECK (reason IN (
        'missing_request', 'ambiguous_close', 'crash_close', 'stale_candidate')),
    CONSTRAINT ck_wpcrc_state CHECK (state IN (
        'unclaimed', 'claiming', 'application_created', 'download_only', 'quarantined', 'expired')),
    CONSTRAINT ck_wpcrc_generation_positive CHECK (generation >= 1),
    CONSTRAINT ck_wpcrc_delivery_key CHECK (wpsync_is_digest(source_delivery_key)),
    CONSTRAINT ck_wpcrc_candidate_confirmation_digest CHECK (
        candidate_confirmation_digest IS NULL OR wpsync_is_digest(candidate_confirmation_digest)),
    CONSTRAINT ck_wpcrc_candidate_contributor_digest CHECK (
        candidate_contributor_digest IS NULL OR wpsync_is_digest(candidate_contributor_digest)),
    CONSTRAINT ck_wpcrc_claimed_bundle_digest CHECK (
        claimed_definition_bundle_sha256 IS NULL OR wpsync_is_digest(claimed_definition_bundle_sha256)),
    -- claim 成功前（unclaimed/claiming）与 download-only/quarantined/expired 终态：三实体恒空
    CONSTRAINT ck_wpcrc_pre_claim_zero_entities CHECK (
        state = 'application_created'
        OR (recovery_request_id IS NULL AND application_id IS NULL AND operation_id IS NULL)),
    -- application_created 必须一次性写入三实体 + claiming participant + prior confirmation + frozen bundle
    CONSTRAINT ck_wpcrc_claimed_all_entities CHECK (
        state <> 'application_created'
        OR (recovery_request_id IS NOT NULL AND application_id IS NOT NULL AND operation_id IS NOT NULL
            AND claimed_by_participant_id IS NOT NULL AND prior_confirmation_id IS NOT NULL
            AND claimed_definition_bundle_id IS NOT NULL AND claimed_definition_bundle_sha256 IS NOT NULL
            AND claimed_at IS NOT NULL)),
    CONSTRAINT uq_wpcrc_claim_idempotency UNIQUE (room_id, generation, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_wpcrc_scope ON working_paper_callback_recovery_case (project_id, wp_id, entry_id, state);
CREATE INDEX IF NOT EXISTS idx_wpcrc_room ON working_paper_callback_recovery_case (room_id, generation, state);

COMMENT ON TABLE working_paper_callback_recovery_case IS
    'V151 durable recovery case：unmatched/ambiguous/crash 的 durable incoming 只绑定它；claim 前 request/application/operation 全空，download-only 三者恒空，claim 成功事务一次性写三实体（Requirement 5.8 / Property 18/68）';

-- recovery case 的 incoming 必须是 durable incoming（quarantined 不得进入 claim 路径）
CREATE OR REPLACE FUNCTION wpsync_check_recovery_incoming() RETURNS trigger AS $fn$
DECLARE
    v_kind text;
    v_state text;
BEGIN
    SELECT a.kind, a.state INTO v_kind, v_state
      FROM working_paper_artifact a WHERE a.id = NEW.incoming_artifact_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'recovery case % 引用不存在的 incoming artifact %', NEW.id, NEW.incoming_artifact_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_kind <> 'incoming' THEN
        RAISE EXCEPTION 'recovery case % 的 artifact kind 必须为 incoming，实得 %', NEW.id, v_kind
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.state = 'application_created' AND v_state <> 'durable' THEN
        RAISE EXCEPTION 'recovery case % claim 成功要求 incoming state=durable，实得 %（quarantined 永不创建 application）', NEW.id, v_state
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpcrc_incoming
    BEFORE INSERT OR UPDATE ON working_paper_callback_recovery_case
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_recovery_incoming();

CREATE TABLE IF NOT EXISTS working_paper_callback_recovery_case_event (
    id BIGSERIAL PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES working_paper_callback_recovery_case(id) ON DELETE RESTRICT,
    sequence_no INTEGER NOT NULL,
    from_state VARCHAR(30),
    to_state VARCHAR(30) NOT NULL,
    actor_type VARCHAR(20) NOT NULL,
    actor_id UUID,
    authorization_result VARCHAR(30),
    prior_confirmation_id UUID
        REFERENCES working_paper_oo_client_confirmation(id) ON DELETE RESTRICT,
    definition_bundle_sha256 CHAR(64),
    error_code VARCHAR(60),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpcrce_sequence UNIQUE (case_id, sequence_no),
    CONSTRAINT ck_wpcrce_sequence_positive CHECK (sequence_no >= 1),
    CONSTRAINT ck_wpcrce_actor_type CHECK (actor_type IN ('user', 'system', 'callback', 'reconciler')),
    CONSTRAINT ck_wpcrce_bundle_digest CHECK (
        definition_bundle_sha256 IS NULL OR wpsync_is_digest(definition_bundle_sha256))
);

CREATE INDEX IF NOT EXISTS idx_wpcrce_case ON working_paper_callback_recovery_case_event (case_id, sequence_no);

COMMENT ON TABLE working_paper_callback_recovery_case_event IS
    'V151 recovery case 独立 append-only timeline（与 operation timeline 分离）：claim 前零 operation 仍可形成 evidence（Requirement 13.5 / Property 68）';

-- ═══════════════════════════════════════════════════════════════════════════
-- 18. working_paper_content_application（design §同名节 / Requirement 4.1 / 5.5 / Property 18/64）
--     application_key 的唯一 owner；immutable origin_request_sequence +
--     单调 effective_request_sequence；incoming FK 只允许 kind=incoming,state=durable。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_content_application (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    entry_id VARCHAR(200) NOT NULL,
    room_id UUID NOT NULL REFERENCES working_paper_oo_room(id) ON DELETE RESTRICT,
    generation INTEGER NOT NULL,
    origin_request_id UUID NOT NULL
        REFERENCES working_paper_forcesave_request(id) ON DELETE RESTRICT,
    application_key CHAR(64) NOT NULL UNIQUE,
    client_edit_epoch BIGINT NOT NULL,
    origin_request_sequence BIGINT NOT NULL,
    effective_request_sequence BIGINT NOT NULL,
    base_version_id UUID NOT NULL REFERENCES working_paper_content_version(id) ON DELETE RESTRICT,
    base_representation_id UUID NOT NULL
        REFERENCES working_paper_content_representation(id) ON DELETE RESTRICT,
    current_revision BIGINT NOT NULL,
    result_revision BIGINT,
    incoming_artifact_id UUID NOT NULL REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    incoming_sha256 CHAR(64) NOT NULL,
    incoming_projection_sha256 CHAR(64),
    merged_projection_sha256 CHAR(64),
    result_representation_id UUID
        REFERENCES working_paper_content_representation(id) ON DELETE RESTRICT,
    result_artifact_sha256 CHAR(64),
    definition_bundle_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_bundle(id) ON DELETE RESTRICT,
    definition_bundle_sha256 CHAR(64) NOT NULL,
    authority_model_definition_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_artifact(id) ON DELETE RESTRICT,
    authority_model_definition_sha256 CHAR(64) NOT NULL,
    adapter_id VARCHAR(120) NOT NULL,
    adapter_build_digest CHAR(64) NOT NULL,
    contributor_snapshot_digest CHAR(64) NOT NULL,
    conflict_count INTEGER NOT NULL DEFAULT 0,
    conflict_set_digest CHAR(64),
    state VARCHAR(30) NOT NULL DEFAULT 'queued',
    superseded_by_application_id UUID
        REFERENCES working_paper_content_application(id) ON DELETE RESTRICT,
    logical_result_code VARCHAR(60),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    durable_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    CONSTRAINT ck_wpca_state CHECK (state IN (
        'queued', 'validating', 'extracting', 'merging', 'conflict', 'rematerializing',
        'applying', 'applied', 'refresh_required', 'error', 'superseded', 'authorization_stale')),
    CONSTRAINT ck_wpca_generation_positive CHECK (generation >= 1),
    CONSTRAINT ck_wpca_application_key CHECK (wpsync_is_digest(application_key)),
    CONSTRAINT ck_wpca_incoming_digest CHECK (wpsync_is_digest(incoming_sha256)),
    CONSTRAINT ck_wpca_incoming_projection_digest CHECK (
        incoming_projection_sha256 IS NULL OR wpsync_is_digest(incoming_projection_sha256)),
    CONSTRAINT ck_wpca_merged_digest CHECK (
        merged_projection_sha256 IS NULL OR wpsync_is_digest(merged_projection_sha256)),
    CONSTRAINT ck_wpca_result_artifact_digest CHECK (
        result_artifact_sha256 IS NULL OR wpsync_is_digest(result_artifact_sha256)),
    CONSTRAINT ck_wpca_bundle_digest CHECK (wpsync_is_digest(definition_bundle_sha256)),
    CONSTRAINT ck_wpca_authority_digest CHECK (wpsync_is_digest(authority_model_definition_sha256)),
    CONSTRAINT ck_wpca_adapter_digest CHECK (wpsync_is_digest(adapter_build_digest)),
    CONSTRAINT ck_wpca_contributor_digest CHECK (wpsync_is_digest(contributor_snapshot_digest)),
    CONSTRAINT ck_wpca_conflict_digest CHECK (
        conflict_set_digest IS NULL OR wpsync_is_digest(conflict_set_digest)),
    CONSTRAINT ck_wpca_sequences CHECK (origin_request_sequence >= 1 AND client_edit_epoch >= 0),
    -- effective sequence 只能 >= origin（GREATEST fold 语义）
    CONSTRAINT ck_wpca_effective_ge_origin CHECK (effective_request_sequence >= origin_request_sequence),
    -- 禁止 self-supersede（同 canonical application 的更高 sequence 只 fold）
    CONSTRAINT ck_wpca_no_self_supersede CHECK (
        superseded_by_application_id IS NULL OR superseded_by_application_id <> id),
    CONSTRAINT ck_wpca_conflict_count_non_negative CHECK (conflict_count >= 0),
    -- result representation 与 digest 成对；applied 必须有 result revision
    CONSTRAINT ck_wpca_result_pair CHECK (
        (result_representation_id IS NULL) = (result_artifact_sha256 IS NULL)),
    CONSTRAINT ck_wpca_applied_requires_result CHECK (
        state <> 'applied'
        OR (result_revision IS NOT NULL AND result_representation_id IS NOT NULL
            AND merged_projection_sha256 IS NOT NULL AND logical_result_code IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_wpca_scope ON working_paper_content_application (project_id, wp_id, entry_id);
CREATE INDEX IF NOT EXISTS idx_wpca_room ON working_paper_content_application (room_id, generation, state);
CREATE INDEX IF NOT EXISTS idx_wpca_incoming ON working_paper_content_application (incoming_artifact_id);

COMMENT ON TABLE working_paper_content_application IS
    'V151 durable incoming 对业务状态的一次逻辑应用；application_key 的唯一 owner（operation 不得复制），key 不含 callback status/request id/room last-applied；incoming FK 只允许 kind=incoming,state=durable（Requirement 5.5 / Property 18/64）';
COMMENT ON COLUMN working_paper_content_application.origin_request_sequence IS
    'immutable：首个 winner request 的 sequence，永不改写';
COMMENT ON COLUMN working_paper_content_application.effective_request_sequence IS
    '单调：同 key 后续 request 命中时 GREATEST(existing, request_sequence)，与 room latest_durable_* 同事务更新';

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_wpoor_latest_durable_application') THEN
        ALTER TABLE working_paper_oo_room ADD CONSTRAINT fk_wpoor_latest_durable_application
            FOREIGN KEY (latest_durable_application_id)
            REFERENCES working_paper_content_application(id) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

-- application 的 incoming 必须是 durable incoming（quarantined 一律拒绝）；
-- result representation 不得等于 incoming；bundle/authority 双向锁死；origin request 一致。
CREATE OR REPLACE FUNCTION wpsync_check_application_identity() RETURNS trigger AS $fn$
DECLARE
    v_kind text;
    v_state text;
    v_sha text;
    v_req_room uuid;
    v_req_generation integer;
    v_req_sequence bigint;
    v_req_bundle uuid;
    v_req_bundle_sha text;
    v_req_authority_sha text;
    v_req_base_version uuid;
    v_req_base_rep uuid;
    v_bundle_authority_id uuid;
BEGIN
    -- incoming artifact 必须 kind=incoming 且 state=durable
    SELECT a.kind, a.state, a.sha256 INTO v_kind, v_state, v_sha
      FROM working_paper_artifact a WHERE a.id = NEW.incoming_artifact_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'application % 引用不存在的 incoming artifact %', NEW.id, NEW.incoming_artifact_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_kind <> 'incoming' THEN
        RAISE EXCEPTION 'application % 的 incoming_artifact_id 必须 kind=incoming，实得 %', NEW.id, v_kind
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_state <> 'durable' THEN
        RAISE EXCEPTION 'application % 的 incoming artifact 必须 state=durable，实得 %（quarantined 永不创建 application）', NEW.id, v_state
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_sha <> NEW.incoming_sha256 THEN
        RAISE EXCEPTION 'application % 的 incoming_sha256 与 artifact 实际 digest 不一致', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    -- origin request 必须同 room/generation，且其冻结 identity 与 application 一致
    SELECT q.room_id, q.generation, q.request_sequence, q.definition_bundle_id,
           q.definition_bundle_sha256, q.authority_model_definition_sha256,
           q.client_base_version_id, q.client_base_representation_id
      INTO v_req_room, v_req_generation, v_req_sequence, v_req_bundle,
           v_req_bundle_sha, v_req_authority_sha, v_req_base_version, v_req_base_rep
      FROM working_paper_forcesave_request q WHERE q.id = NEW.origin_request_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'application % 引用不存在的 origin request %', NEW.id, NEW.origin_request_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_req_room <> NEW.room_id OR v_req_generation <> NEW.generation THEN
        RAISE EXCEPTION 'application % 的 origin request 跨 room/generation', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_req_sequence <> NEW.origin_request_sequence THEN
        RAISE EXCEPTION 'application % 的 origin_request_sequence % 必须等于 origin request 的 request_sequence %',
            NEW.id, NEW.origin_request_sequence, v_req_sequence
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_req_bundle <> NEW.definition_bundle_id
       OR v_req_bundle_sha <> NEW.definition_bundle_sha256
       OR v_req_authority_sha <> NEW.authority_model_definition_sha256 THEN
        RAISE EXCEPTION 'application % 的 bundle/authority identity 必须来自 origin request 的冻结值', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_req_base_version <> NEW.base_version_id OR v_req_base_rep <> NEW.base_representation_id THEN
        RAISE EXCEPTION 'application % 的 frozen client base 必须来自 origin request', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    -- bundle 的 authority child 必须与 application 的 authority FK 一致
    SELECT b.authority_model_definition_id INTO v_bundle_authority_id
      FROM working_paper_sync_definition_bundle b WHERE b.id = NEW.definition_bundle_id;
    IF v_bundle_authority_id IS DISTINCT FROM NEW.authority_model_definition_id THEN
        RAISE EXCEPTION 'application % 的 authority model 与 bundle child 未双向锁死', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpca_identity
    BEFORE INSERT OR UPDATE ON working_paper_content_application
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_application_identity();

-- identity 不可变 + effective sequence 单调（GREATEST fold）+ origin 永不改写
CREATE OR REPLACE FUNCTION wpsync_check_application_mutation() RETURNS trigger AS $fn$
BEGIN
    IF NEW.application_key IS DISTINCT FROM OLD.application_key
       OR NEW.project_id IS DISTINCT FROM OLD.project_id
       OR NEW.wp_id IS DISTINCT FROM OLD.wp_id
       OR NEW.entry_id IS DISTINCT FROM OLD.entry_id
       OR NEW.room_id IS DISTINCT FROM OLD.room_id
       OR NEW.generation IS DISTINCT FROM OLD.generation
       OR NEW.origin_request_id IS DISTINCT FROM OLD.origin_request_id
       OR NEW.origin_request_sequence IS DISTINCT FROM OLD.origin_request_sequence
       OR NEW.base_version_id IS DISTINCT FROM OLD.base_version_id
       OR NEW.base_representation_id IS DISTINCT FROM OLD.base_representation_id
       OR NEW.incoming_artifact_id IS DISTINCT FROM OLD.incoming_artifact_id
       OR NEW.incoming_sha256 IS DISTINCT FROM OLD.incoming_sha256
       OR NEW.definition_bundle_id IS DISTINCT FROM OLD.definition_bundle_id
       OR NEW.definition_bundle_sha256 IS DISTINCT FROM OLD.definition_bundle_sha256
       OR NEW.authority_model_definition_id IS DISTINCT FROM OLD.authority_model_definition_id
       OR NEW.authority_model_definition_sha256 IS DISTINCT FROM OLD.authority_model_definition_sha256
       OR NEW.adapter_id IS DISTINCT FROM OLD.adapter_id
       OR NEW.adapter_build_digest IS DISTINCT FROM OLD.adapter_build_digest THEN
        RAISE EXCEPTION 'content application 的 identity 列（application_key/scope/origin request+sequence/frozen base/incoming/bundle/authority/adapter）不可变 (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.effective_request_sequence < OLD.effective_request_sequence THEN
        RAISE EXCEPTION 'effective_request_sequence 只可单调提升（%→%）', OLD.effective_request_sequence, NEW.effective_request_sequence
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpca_mutation
    BEFORE UPDATE ON working_paper_content_application
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_application_mutation();

-- application sequence fold 的 append-only timeline（与 operation timeline 分离但同事务写）
CREATE TABLE IF NOT EXISTS working_paper_content_application_event (
    id BIGSERIAL PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES working_paper_content_application(id) ON DELETE RESTRICT,
    sequence_no INTEGER NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    from_state VARCHAR(30),
    to_state VARCHAR(30),
    folded_request_id UUID REFERENCES working_paper_forcesave_request(id) ON DELETE RESTRICT,
    origin_request_sequence BIGINT NOT NULL,
    effective_request_sequence BIGINT NOT NULL,
    room_latest_durable_sequence BIGINT,
    actor_type VARCHAR(20) NOT NULL,
    actor_id UUID,
    error_code VARCHAR(60),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpcae_sequence UNIQUE (application_id, sequence_no),
    CONSTRAINT ck_wpcae_sequence_positive CHECK (sequence_no >= 1),
    CONSTRAINT ck_wpcae_event_type CHECK (event_type IN (
        'created', 'sequence_folded', 'state_changed', 'superseded', 'terminal')),
    CONSTRAINT ck_wpcae_actor_type CHECK (actor_type IN ('user', 'system', 'callback', 'reconciler')),
    CONSTRAINT ck_wpcae_effective_ge_origin CHECK (effective_request_sequence >= origin_request_sequence),
    -- sequence_folded 必须记录被折叠的 request（否则无法审计 fold 来源）
    CONSTRAINT ck_wpcae_fold_requires_request CHECK (
        event_type <> 'sequence_folded' OR folded_request_id IS NOT NULL),
    -- 同 application 的 fold 必须同事务写 room durable fence
    CONSTRAINT ck_wpcae_fold_requires_room_fence CHECK (
        event_type <> 'sequence_folded' OR room_latest_durable_sequence IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_wpcae_application ON working_paper_content_application_event (application_id, sequence_no);
-- 同一 request 对同一 application 只能 fold 一次（幂等重放不得产生第二 event）
CREATE UNIQUE INDEX IF NOT EXISTS uq_wpcae_fold_once
    ON working_paper_content_application_event (application_id, folded_request_id)
    WHERE event_type = 'sequence_folded';

COMMENT ON TABLE working_paper_content_application_event IS
    'V151 application append-only timeline：sequence_folded 与 room latest durable fence 同事务写且同 request 只写一次；origin sequence 不得改写（Property 68 / Requirement 5.10）';

-- ═══════════════════════════════════════════════════════════════════════════
-- 19. working_paper_sync_operation（design §同名节 / Property 18/64）
--     application_id 为 nullable UNIQUE primary FK；duplicate_of_operation_id 为
--     nullable direct self FK；terminal `duplicate` 状态。
--     winner primary 绑定 application；loser shell 保持 application 空并直指 primary。
--     禁止 self / 链 / 环；operation 不得保存 application_key。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_sync_operation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    entry_id VARCHAR(200) NOT NULL,
    room_id UUID REFERENCES working_paper_oo_room(id) ON DELETE RESTRICT,
    forcesave_request_id UUID REFERENCES working_paper_forcesave_request(id) ON DELETE RESTRICT,
    application_id UUID REFERENCES working_paper_content_application(id) ON DELETE RESTRICT,
    duplicate_of_operation_id UUID REFERENCES working_paper_sync_operation(id) ON DELETE RESTRICT,
    initiated_by_participant_id UUID REFERENCES working_paper_oo_participant(id) ON DELETE RESTRICT,
    direction VARCHAR(30) NOT NULL,
    state VARCHAR(30) NOT NULL DEFAULT 'created',
    definition_bundle_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_bundle(id) ON DELETE RESTRICT,
    definition_bundle_sha256 CHAR(64) NOT NULL,
    authority_model_definition_id UUID NOT NULL
        REFERENCES working_paper_sync_definition_artifact(id) ON DELETE RESTRICT,
    authority_model_definition_sha256 CHAR(64) NOT NULL,
    error_code VARCHAR(60),
    error_stage VARCHAR(40),
    error_detail TEXT,
    accepted_at TIMESTAMPTZ,
    application_bound_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- application 的 primary owner 唯一：一个 application 最多绑定一个 operation
    CONSTRAINT uq_wpso_application UNIQUE (application_id),
    -- 每个 request 最多一个 shell
    CONSTRAINT uq_wpso_request UNIQUE (forcesave_request_id),
    CONSTRAINT ck_wpso_direction CHECK (direction IN (
        'html_to_oo', 'oo_to_html', 'conflict_resolution', 'rollback')),
    CONSTRAINT ck_wpso_state CHECK (state IN (
        'created', 'command_pending', 'accepted', 'waiting_application', 'application_bound',
        'duplicate', 'extracting', 'merging', 'conflict', 'rematerializing', 'applying',
        'applied', 'refresh_required', 'error', 'rejected', 'superseded', 'authorization_stale')),
    CONSTRAINT ck_wpso_bundle_digest CHECK (wpsync_is_digest(definition_bundle_sha256)),
    CONSTRAINT ck_wpso_authority_digest CHECK (wpsync_is_digest(authority_model_definition_sha256)),
    -- primary / duplicate / pre-correlation 三态互斥：绝不同时绑定 application 与 duplicate 指针
    CONSTRAINT ck_wpso_not_both_owners CHECK (
        application_id IS NULL OR duplicate_of_operation_id IS NULL),
    -- 禁 self-reference
    CONSTRAINT ck_wpso_no_self_duplicate CHECK (
        duplicate_of_operation_id IS NULL OR duplicate_of_operation_id <> id),
    -- duplicate 必为 terminal 且 application 空
    CONSTRAINT ck_wpso_duplicate_shape CHECK (
        (duplicate_of_operation_id IS NULL AND state <> 'duplicate')
        OR (duplicate_of_operation_id IS NOT NULL AND state = 'duplicate' AND application_id IS NULL)),
    -- application_bound 状态必须真的绑定了 application
    CONSTRAINT ck_wpso_bound_requires_application CHECK (
        state <> 'application_bound' OR application_id IS NOT NULL),
    CONSTRAINT ck_wpso_bound_at CHECK (
        (application_id IS NULL) = (application_bound_at IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_wpso_scope ON working_paper_sync_operation (project_id, wp_id, entry_id);
CREATE INDEX IF NOT EXISTS idx_wpso_room_state ON working_paper_sync_operation (room_id, state);
CREATE INDEX IF NOT EXISTS idx_wpso_duplicate ON working_paper_sync_operation (duplicate_of_operation_id);

COMMENT ON TABLE working_paper_sync_operation IS
    'V151 用户轮询/执行/timeline 容器，不承担 application identity：normal accepted shell 初始 application_id=NULL；winner primary 在 durable correlation 后绑定，loser shell 保持 application 空并直指 primary 且 state=duplicate；本表禁止出现 application_key 列（Property 18/64）';
COMMENT ON COLUMN working_paper_sync_operation.application_id IS
    'nullable UNIQUE primary FK：pre-correlation 为 NULL 是合法态；duplicate 永远为 NULL';
COMMENT ON COLUMN working_paper_sync_operation.duplicate_of_operation_id IS
    'nullable direct self FK：只能直指同 scope/同 frozen bundle 且已绑定该 application 的 primary，禁止 self/链/环';

-- duplicate 目标必须是 primary（⇒ 结构性排除链与环）、同 scope、同 frozen bundle
CREATE OR REPLACE FUNCTION wpsync_check_operation_duplicate_link() RETURNS trigger AS $fn$
DECLARE
    v_t_project uuid;
    v_t_wp uuid;
    v_t_entry text;
    v_t_room uuid;
    v_t_application uuid;
    v_t_duplicate uuid;
    v_t_state text;
    v_t_bundle uuid;
    v_t_bundle_sha text;
    v_t_authority_sha text;
    v_t_app_generation integer;
    v_my_generation integer;
BEGIN
    IF NEW.duplicate_of_operation_id IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT o.project_id, o.wp_id, o.entry_id, o.room_id, o.application_id,
           o.duplicate_of_operation_id, o.state, o.definition_bundle_id,
           o.definition_bundle_sha256, o.authority_model_definition_sha256
      INTO v_t_project, v_t_wp, v_t_entry, v_t_room, v_t_application,
           v_t_duplicate, v_t_state, v_t_bundle, v_t_bundle_sha, v_t_authority_sha
      FROM working_paper_sync_operation o WHERE o.id = NEW.duplicate_of_operation_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'operation % 的 duplicate_of_operation_id % 不存在', NEW.id, NEW.duplicate_of_operation_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    -- 目标必须是 direct primary：已绑定 application **且**自身不是 duplicate。
    --
    -- 🔴 这里刻意写成**一条**断言而不是两条。行级 CHECK `ck_wpso_duplicate_shape` 已经
    --    强制「凡 duplicate 必 application_id IS NULL」，因此「目标是 duplicate」这件事
    --    永远同时满足「目标未绑定 application」——拆成两条断言时，无论谁在前，后一条
    --    都会遮蔽前一条，使被遮蔽的那条分支成为**不可达代码**（变异检验实测判 GREEN，
    --    即守卫无法证明它有效）。合并为单条既消掉不可达分支，也让 chain/环与 stranded
    --    两种形态在同一处报出，禁止 self（由 CHECK 保证）、链、环与 stranded duplicate。
    IF v_t_application IS NULL OR v_t_duplicate IS NOT NULL OR v_t_state = 'duplicate' THEN
        RAISE EXCEPTION 'operation % 的 duplicate 目标 % 不是 direct primary（application_id=%, duplicate_of=%, state=%）：禁止链/环与 stranded duplicate',
            NEW.id, NEW.duplicate_of_operation_id, v_t_application, v_t_duplicate, v_t_state
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_t_project <> NEW.project_id OR v_t_wp <> NEW.wp_id
       OR v_t_entry <> NEW.entry_id OR v_t_room IS DISTINCT FROM NEW.room_id THEN
        RAISE EXCEPTION 'operation % 的 duplicate 目标跨 scope（project/wp/entry/room 必须相同）', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_t_bundle <> NEW.definition_bundle_id
       OR v_t_bundle_sha <> NEW.definition_bundle_sha256
       OR v_t_authority_sha <> NEW.authority_model_definition_sha256 THEN
        RAISE EXCEPTION 'operation % 的 duplicate 目标 frozen bundle/authority 不同（同 key 折叠要求同 bundle）', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    -- generation 也必须相同（application 携带 generation）
    SELECT c.generation INTO v_t_app_generation
      FROM working_paper_content_application c WHERE c.id = v_t_application;
    SELECT q.generation INTO v_my_generation
      FROM working_paper_forcesave_request q WHERE q.id = NEW.forcesave_request_id;
    IF v_my_generation IS NOT NULL AND v_t_app_generation IS NOT NULL
       AND v_my_generation <> v_t_app_generation THEN
        RAISE EXCEPTION 'operation % 的 duplicate 目标 application 跨 generation（% vs %）', NEW.id, v_my_generation, v_t_app_generation
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

DO $$ BEGIN
    -- 🔴 存在性守卫必须**限定到本次目标表**（`tgrelid = regclass`），不能只按 tgname 全库查。
    -- 只按 tgname 查时，任何一个 schema 里存在同名触发器（例如 public 已应用过本迁移，
    -- 或 scratch schema 测试残留）都会让后续 schema 静默跳过创建 —— 表现为
    -- 「迁移 apply_errors=0 但 3 个 CONSTRAINT TRIGGER 一个都没建起来」。
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgname = 'trg_wpso_duplicate_link'
           AND tgrelid = 'working_paper_sync_operation'::regclass
    ) THEN
        CREATE CONSTRAINT TRIGGER trg_wpso_duplicate_link
            AFTER INSERT OR UPDATE ON working_paper_sync_operation
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION wpsync_check_operation_duplicate_link();
    END IF;
END $$;

-- primary 绑定的 application 必须同 scope/同 frozen bundle；operation 的 bundle 与 request 一致
CREATE OR REPLACE FUNCTION wpsync_check_operation_application_link() RETURNS trigger AS $fn$
DECLARE
    v_a_project uuid;
    v_a_wp uuid;
    v_a_entry text;
    v_a_room uuid;
    v_a_bundle uuid;
    v_a_bundle_sha text;
    v_a_authority_sha text;
    v_r_bundle uuid;
    v_r_bundle_sha text;
BEGIN
    IF NEW.forcesave_request_id IS NOT NULL THEN
        SELECT q.definition_bundle_id, q.definition_bundle_sha256 INTO v_r_bundle, v_r_bundle_sha
          FROM working_paper_forcesave_request q WHERE q.id = NEW.forcesave_request_id;
        IF v_r_bundle IS DISTINCT FROM NEW.definition_bundle_id
           OR v_r_bundle_sha IS DISTINCT FROM NEW.definition_bundle_sha256 THEN
            RAISE EXCEPTION 'operation % 的 frozen bundle 必须与 forcesave request 一致', NEW.id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF NEW.application_id IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT c.project_id, c.wp_id, c.entry_id, c.room_id, c.definition_bundle_id,
           c.definition_bundle_sha256, c.authority_model_definition_sha256
      INTO v_a_project, v_a_wp, v_a_entry, v_a_room, v_a_bundle, v_a_bundle_sha, v_a_authority_sha
      FROM working_paper_content_application c WHERE c.id = NEW.application_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'operation % 绑定不存在的 application %', NEW.id, NEW.application_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_a_project <> NEW.project_id OR v_a_wp <> NEW.wp_id
       OR v_a_entry <> NEW.entry_id OR v_a_room IS DISTINCT FROM NEW.room_id THEN
        RAISE EXCEPTION 'operation % 绑定的 application 跨 scope', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_a_bundle <> NEW.definition_bundle_id
       OR v_a_bundle_sha <> NEW.definition_bundle_sha256
       OR v_a_authority_sha <> NEW.authority_model_definition_sha256 THEN
        RAISE EXCEPTION 'operation % 与所绑定 application 的 frozen bundle/authority 不一致', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgname = 'trg_wpso_application_link'
           AND tgrelid = 'working_paper_sync_operation'::regclass
    ) THEN
        CREATE CONSTRAINT TRIGGER trg_wpso_application_link
            AFTER INSERT OR UPDATE ON working_paper_sync_operation
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION wpsync_check_operation_application_link();
    END IF;
END $$;

-- 一旦绑定 application 即不可改绑/解绑；duplicate 指针一旦写入即不可改
CREATE OR REPLACE FUNCTION wpsync_check_operation_binding_immutable() RETURNS trigger AS $fn$
BEGIN
    IF OLD.application_id IS NOT NULL AND NEW.application_id IS DISTINCT FROM OLD.application_id THEN
        RAISE EXCEPTION 'operation % 已绑定 application，禁止改绑/解绑（禁止 duplicate→primary 重定向）', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.duplicate_of_operation_id IS NOT NULL
       AND NEW.duplicate_of_operation_id IS DISTINCT FROM OLD.duplicate_of_operation_id THEN
        RAISE EXCEPTION 'operation % 的 duplicate 指针不可变（删除/改指均禁止）', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.state = 'duplicate' AND NEW.state <> 'duplicate' THEN
        RAISE EXCEPTION 'operation % 的 duplicate 是 terminal 状态，禁止再流转', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpso_binding_immutable
    BEFORE UPDATE ON working_paper_sync_operation
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_operation_binding_immutable();

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_wpcrc_operation') THEN
        ALTER TABLE working_paper_callback_recovery_case ADD CONSTRAINT fk_wpcrc_operation
            FOREIGN KEY (operation_id)
            REFERENCES working_paper_sync_operation(id) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_wpcrc_application') THEN
        ALTER TABLE working_paper_callback_recovery_case ADD CONSTRAINT fk_wpcrc_application
            FOREIGN KEY (application_id)
            REFERENCES working_paper_content_application(id) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_wpcv_operation') THEN
        ALTER TABLE working_paper_content_version ADD CONSTRAINT fk_wpcv_operation
            FOREIGN KEY (operation_id)
            REFERENCES working_paper_sync_operation(id) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_wppm_result_operation') THEN
        ALTER TABLE working_paper_pending_mutation ADD CONSTRAINT fk_wppm_result_operation
            FOREIGN KEY (result_operation_id)
            REFERENCES working_paper_sync_operation(id) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_wpa_created_by_operation') THEN
        ALTER TABLE working_paper_artifact ADD CONSTRAINT fk_wpa_created_by_operation
            FOREIGN KEY (created_by_operation_id)
            REFERENCES working_paper_sync_operation(id) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════════
-- 20. working_paper_sync_operation_event / _contributor（design §同名节 / Requirement 5.10 / 13.5）
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_sync_operation_event (
    id BIGSERIAL PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES working_paper_sync_operation(id) ON DELETE RESTRICT,
    sequence_no INTEGER NOT NULL,
    from_state VARCHAR(30),
    to_state VARCHAR(30) NOT NULL,
    stage VARCHAR(40),
    error_code VARCHAR(60),
    actor_type VARCHAR(20) NOT NULL,
    actor_id UUID,
    correlation_id UUID,
    client_edit_epoch BIGINT,
    origin_request_sequence BIGINT,
    effective_request_sequence BIGINT,
    superseded_by UUID,
    detail_digest CHAR(64),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpsoe_sequence UNIQUE (operation_id, sequence_no),
    CONSTRAINT ck_wpsoe_sequence_positive CHECK (sequence_no >= 1),
    CONSTRAINT ck_wpsoe_actor_type CHECK (actor_type IN ('user', 'system', 'callback', 'reconciler')),
    CONSTRAINT ck_wpsoe_detail_digest CHECK (detail_digest IS NULL OR wpsync_is_digest(detail_digest))
);

CREATE INDEX IF NOT EXISTS idx_wpsoe_operation ON working_paper_sync_operation_event (operation_id, sequence_no);
-- primary 的 application_bound 与 duplicate 的 terminal event 在同一 operation 内各自唯一
CREATE UNIQUE INDEX IF NOT EXISTS uq_wpsoe_application_bound_once
    ON working_paper_sync_operation_event (operation_id)
    WHERE to_state = 'application_bound';
CREATE UNIQUE INDEX IF NOT EXISTS uq_wpsoe_duplicate_once
    ON working_paper_sync_operation_event (operation_id)
    WHERE to_state = 'duplicate';

COMMENT ON TABLE working_paper_sync_operation_event IS
    'V151 operation append-only timeline：current state 只是 timeline 投影；application_bound 与 duplicate 各自在同 operation 内恰一个 event（Requirement 5.10 / 13.5 / Property 68）';

CREATE TABLE IF NOT EXISTS working_paper_sync_operation_contributor (
    operation_id UUID NOT NULL REFERENCES working_paper_sync_operation(id) ON DELETE RESTRICT,
    participant_id UUID NOT NULL REFERENCES working_paper_oo_participant(id) ON DELETE RESTRICT,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    permission_epoch BIGINT NOT NULL,
    source VARCHAR(30) NOT NULL,
    confidence VARCHAR(20) NOT NULL,
    CONSTRAINT pk_wpsoc PRIMARY KEY (operation_id, participant_id),
    CONSTRAINT ck_wpsoc_source CHECK (source IN ('request_initiator', 'oo_users', 'active_writer_snapshot')),
    CONSTRAINT ck_wpsoc_confidence CHECK (confidence IN ('exact', 'aggregate', 'unknown')),
    CONSTRAINT ck_wpsoc_epoch CHECK (permission_epoch >= 0)
);

COMMENT ON TABLE working_paper_sync_operation_contributor IS
    'V151 contributor set：route participant 不等于唯一作者；aggregate/unknown 且有被撤销 writer 时安全策略是不应用并旋转 generation（design §同名节）';

-- ═══════════════════════════════════════════════════════════════════════════
-- 21. working_paper_callback_delivery（design §同名节 / Requirement 5.4 / Property 18）
--     归属只按 durable_at 判定；application 与 recovery 是 XOR；request 与 application 不做 XOR。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_callback_delivery (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    wp_id UUID NOT NULL REFERENCES working_paper(id) ON DELETE RESTRICT,
    entry_id VARCHAR(200) NOT NULL,
    room_id UUID NOT NULL REFERENCES working_paper_oo_room(id) ON DELETE RESTRICT,
    generation INTEGER NOT NULL,
    operation_id UUID REFERENCES working_paper_sync_operation(id) ON DELETE RESTRICT,
    application_id UUID REFERENCES working_paper_content_application(id) ON DELETE RESTRICT,
    forcesave_request_id UUID REFERENCES working_paper_forcesave_request(id) ON DELETE RESTRICT,
    callback_recovery_case_id UUID
        REFERENCES working_paper_callback_recovery_case(id) ON DELETE RESTRICT,
    route_credential_id UUID NOT NULL,
    callback_status INTEGER NOT NULL,
    delivery_key CHAR(64) NOT NULL UNIQUE,
    state VARCHAR(20) NOT NULL DEFAULT 'received',
    payload_sha256 CHAR(64),
    oo_users_digest CHAR(64),
    correlation_result VARCHAR(30),
    incoming_artifact_id UUID REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    response_error INTEGER,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    durable_at TIMESTAMPTZ,
    responded_at TIMESTAMPTZ,
    CONSTRAINT ck_wpcd_generation_positive CHECK (generation >= 1),
    CONSTRAINT ck_wpcd_state CHECK (state IN (
        'received', 'downloading', 'durable', 'acknowledged', 'rejected', 'error', 'unmatched')),
    CONSTRAINT ck_wpcd_delivery_key CHECK (wpsync_is_digest(delivery_key)),
    CONSTRAINT ck_wpcd_payload_digest CHECK (payload_sha256 IS NULL OR wpsync_is_digest(payload_sha256)),
    CONSTRAINT ck_wpcd_users_digest CHECK (oo_users_digest IS NULL OR wpsync_is_digest(oo_users_digest)),
    CONSTRAINT ck_wpcd_correlation_result CHECK (correlation_result IS NULL OR correlation_result IN (
        'request', 'existing_application', 'close_capture', 'unmatched', 'ambiguous')),
    -- 任何阶段都禁止双 owner
    CONSTRAINT ck_wpcd_no_double_owner CHECK (
        application_id IS NULL OR callback_recovery_case_id IS NULL),
    -- durable fact 存在 ⇒ 恰属两类之一（application XOR recovery）
    CONSTRAINT ck_wpcd_durable_exactly_one_owner CHECK (
        durable_at IS NULL
        OR ((application_id IS NOT NULL) <> (callback_recovery_case_id IS NOT NULL))),
    -- durable state 必须有 durable_at（禁止把泛化 terminal 当 durable）
    CONSTRAINT ck_wpcd_durable_state_requires_fact CHECK (
        state NOT IN ('durable', 'acknowledged', 'unmatched') OR durable_at IS NOT NULL),
    -- unmatched/ambiguous：recovery 非空且 request/application/operation 全空
    CONSTRAINT ck_wpcd_unmatched_zero_entities CHECK (
        state <> 'unmatched'
        OR (callback_recovery_case_id IS NOT NULL
            AND application_id IS NULL AND operation_id IS NULL AND forcesave_request_id IS NULL)),
    CONSTRAINT ck_wpcd_ambiguous_zero_entities CHECK (
        correlation_result IS NULL
        OR correlation_result NOT IN ('unmatched', 'ambiguous')
        OR (application_id IS NULL AND operation_id IS NULL AND forcesave_request_id IS NULL)),
    -- durable 且 correlated 必须绑定 incoming artifact
    CONSTRAINT ck_wpcd_durable_requires_incoming CHECK (
        durable_at IS NULL OR incoming_artifact_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_wpcd_scope ON working_paper_callback_delivery (project_id, wp_id, entry_id);
CREATE INDEX IF NOT EXISTS idx_wpcd_room ON working_paper_callback_delivery (room_id, generation, callback_status);
CREATE INDEX IF NOT EXISTS idx_wpcd_application ON working_paper_callback_delivery (application_id);
CREATE INDEX IF NOT EXISTS idx_wpcd_recovery ON working_paper_callback_delivery (callback_recovery_case_id);

COMMENT ON TABLE working_paper_callback_delivery IS
    'V151 callback delivery：delivery_key 含 status + discriminator 故同 application 可有多 delivery；归属只按 immutable durable_at 判定，application/recovery XOR，request 与 application 不做 XOR（Requirement 5.4 / Property 18）';

-- delivery 引用 primary 时 operation.application_id = delivery.application_id；
-- 引用 terminal duplicate 时该 operation application 为空且其 direct primary 的 application 相等。
CREATE OR REPLACE FUNCTION wpsync_check_delivery_operation_link() RETURNS trigger AS $fn$
DECLARE
    v_op_application uuid;
    v_op_duplicate uuid;
    v_primary_application uuid;
BEGIN
    IF NEW.operation_id IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT o.application_id, o.duplicate_of_operation_id INTO v_op_application, v_op_duplicate
      FROM working_paper_sync_operation o WHERE o.id = NEW.operation_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'delivery % 引用不存在的 operation %', NEW.id, NEW.operation_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    IF NEW.application_id IS NULL THEN
        -- pre-correlation：可保留已精确绑定的 request/operation shell，但 shell 不得已绑定别的 application
        IF v_op_application IS NOT NULL THEN
            RAISE EXCEPTION 'delivery % 未归组却引用了已绑定 application 的 primary operation %', NEW.id, NEW.operation_id
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NULL;
    END IF;

    IF v_op_duplicate IS NULL THEN
        IF v_op_application IS DISTINCT FROM NEW.application_id THEN
            RAISE EXCEPTION 'delivery % 引用 primary operation 时要求 operation.application_id = delivery.application_id', NEW.id
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NULL;
    END IF;

    -- duplicate 支：自身 application 必空，其 direct primary 的 application 必须等于 delivery
    IF v_op_application IS NOT NULL THEN
        RAISE EXCEPTION 'delivery % 引用的 duplicate operation 不得自身绑定 application', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT p.application_id INTO v_primary_application
      FROM working_paper_sync_operation p WHERE p.id = v_op_duplicate;
    IF v_primary_application IS DISTINCT FROM NEW.application_id THEN
        RAISE EXCEPTION 'delivery % 引用 duplicate operation 时要求其 direct primary 的 application 等于 delivery.application_id', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgname = 'trg_wpcd_operation_link'
           AND tgrelid = 'working_paper_callback_delivery'::regclass
    ) THEN
        CREATE CONSTRAINT TRIGGER trg_wpcd_operation_link
            AFTER INSERT OR UPDATE ON working_paper_callback_delivery
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION wpsync_check_delivery_operation_link();
    END IF;
END $$;

-- durable_at 是 immutable durable fact：一经写入不得清空或改写
CREATE OR REPLACE FUNCTION wpsync_check_delivery_durable_fact() RETURNS trigger AS $fn$
BEGIN
    IF OLD.durable_at IS NOT NULL AND NEW.durable_at IS DISTINCT FROM OLD.durable_at THEN
        RAISE EXCEPTION 'delivery % 的 durable_at 是 immutable durable fact，禁止清空或改写', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.delivery_key IS DISTINCT FROM OLD.delivery_key THEN
        RAISE EXCEPTION 'delivery % 的 delivery_key 不可变', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    -- post-durable error 必须保留既有 owner
    IF OLD.durable_at IS NOT NULL AND OLD.application_id IS NOT NULL
       AND NEW.application_id IS NULL THEN
        RAISE EXCEPTION 'delivery % post-durable 不得丢弃 application owner', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.durable_at IS NOT NULL AND OLD.callback_recovery_case_id IS NOT NULL
       AND NEW.callback_recovery_case_id IS NULL THEN
        RAISE EXCEPTION 'delivery % post-durable 不得丢弃 recovery owner', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpcd_durable_fact
    BEFORE UPDATE ON working_paper_callback_delivery
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_delivery_durable_fact();

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_wpa_source_delivery') THEN
        ALTER TABLE working_paper_artifact ADD CONSTRAINT fk_wpa_source_delivery
            FOREIGN KEY (source_delivery_id)
            REFERENCES working_paper_callback_delivery(id) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════════
-- 22. working_paper_sync_conflict（design §同名节 / Requirement 8.1）
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_sync_conflict (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_id UUID NOT NULL REFERENCES working_paper_sync_operation(id) ON DELETE RESTRICT,
    client_edit_epoch BIGINT NOT NULL,
    canonical_application_id UUID
        REFERENCES working_paper_content_application(id) ON DELETE RESTRICT,
    effective_request_sequence BIGINT,
    stable_field_key VARCHAR(300) NOT NULL,
    business_label VARCHAR(300) NOT NULL,
    sheet_key VARCHAR(200),
    table_key VARCHAR(200),
    row_key VARCHAR(200) NOT NULL DEFAULT '',
    json_pointer TEXT NOT NULL,
    oo_location TEXT NOT NULL DEFAULT '',
    field_source VARCHAR(40) NOT NULL,
    protection_policy VARCHAR(40) NOT NULL,
    suggested_action VARCHAR(40) NOT NULL,
    conflict_kind VARCHAR(30) NOT NULL,
    base_value JSONB,
    current_value JSONB,
    incoming_value JSONB,
    resolution JSONB,
    resolved_value JSONB,
    resolved_by UUID REFERENCES users(id) ON DELETE RESTRICT,
    resolved_at TIMESTAMPTZ,
    superseded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpsc_field UNIQUE (operation_id, stable_field_key, row_key, oo_location),
    CONSTRAINT ck_wpsc_conflict_kind CHECK (conflict_kind IN (
        'value', 'protected', 'delete_update', 'schema', 'duplicate_word_instance')),
    CONSTRAINT ck_wpsc_stable_key_non_empty CHECK (length(btrim(stable_field_key)) > 0),
    CONSTRAINT ck_wpsc_label_non_empty CHECK (length(btrim(business_label)) > 0),
    CONSTRAINT ck_wpsc_json_pointer CHECK (json_pointer = '' OR json_pointer LIKE '/%'),
    CONSTRAINT ck_wpsc_resolution_pair CHECK ((resolved_at IS NULL) = (resolved_by IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_wpsc_operation ON working_paper_sync_conflict (operation_id);
CREATE INDEX IF NOT EXISTS idx_wpsc_group ON working_paper_sync_conflict (operation_id, sheet_key, table_key, row_key);

COMMENT ON TABLE working_paper_sync_conflict IS
    'V151 冲突记录：stable field key + 业务标签 + JSON Pointer/OO 位置 + base/current/incoming 三值 + 字段来源/保护策略/建议动作（Requirement 8.1）';

-- ═══════════════════════════════════════════════════════════════════════════
-- 23. working_paper_sync_test_run / working_paper_entry_evidence_scenario
--     （design §同名节 / Requirement 12.10 / 12.11 / Property 69）
--     evidence 由持久化不可变实体 + 服务端重算闭合；download-only 场景零 operation/application。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_sync_test_run (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id VARCHAR(200) NOT NULL,
    source_commit VARCHAR(80) NOT NULL,
    runner_version VARCHAR(40) NOT NULL,
    manifest_source_digest CHAR(64) NOT NULL,
    editability VARCHAR(20) NOT NULL,
    room_model VARCHAR(20) NOT NULL,
    scenario_profile_digest CHAR(64) NOT NULL,
    onlyoffice_build VARCHAR(60) NOT NULL,
    browser_build VARCHAR(120) NOT NULL,
    environment_digest CHAR(64) NOT NULL,
    required_scenario_set_digest CHAR(64) NOT NULL,
    authority_model_definition_sha256 CHAR(64) NOT NULL,
    definition_bundle_sha256 CHAR(64) NOT NULL,
    run_manifest_artifact_id UUID NOT NULL REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    run_manifest_sha256 CHAR(64) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    aggregate_result VARCHAR(20) NOT NULL DEFAULT 'unverified',
    CONSTRAINT ck_wpstr_editability CHECK (editability IN ('editable', 'readonly', 'unreachable')),
    CONSTRAINT ck_wpstr_room_model CHECK (room_model IN ('shared', 'exclusive', 'none')),
    CONSTRAINT ck_wpstr_aggregate_result CHECK (aggregate_result IN ('unverified', 'passed', 'failed')),
    CONSTRAINT ck_wpstr_manifest_digest CHECK (wpsync_is_digest(manifest_source_digest)),
    CONSTRAINT ck_wpstr_profile_digest CHECK (wpsync_is_digest(scenario_profile_digest)),
    CONSTRAINT ck_wpstr_environment_digest CHECK (wpsync_is_digest(environment_digest)),
    CONSTRAINT ck_wpstr_required_set_digest CHECK (wpsync_is_digest(required_scenario_set_digest)),
    CONSTRAINT ck_wpstr_authority_digest CHECK (wpsync_is_digest(authority_model_definition_sha256)),
    CONSTRAINT ck_wpstr_bundle_digest CHECK (wpsync_is_digest(definition_bundle_sha256)),
    CONSTRAINT ck_wpstr_run_manifest_digest CHECK (wpsync_is_digest(run_manifest_sha256)),
    -- 结果只能在 finished 后判定（禁止自填 verified_at 式的空结果）
    CONSTRAINT ck_wpstr_result_requires_finish CHECK (
        aggregate_result = 'unverified' OR finished_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_wpstr_entry ON working_paper_sync_test_run (entry_id, started_at DESC);

COMMENT ON TABLE working_paper_sync_test_run IS
    'V151 sync test run：source-backed manifest profile（editability/room_model/scenario_profile_digest）+ capability + frozen bundle/authority 推导 required_scenario_set_digest；aggregate_result 由服务端重算，不可自由文本覆写（Requirement 12.10 / Property 69）';

CREATE TABLE IF NOT EXISTS working_paper_entry_evidence_scenario (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES working_paper_sync_test_run(id) ON DELETE RESTRICT,
    scenario_id VARCHAR(120) NOT NULL,
    ordinal INTEGER NOT NULL,
    scenario_kind VARCHAR(30) NOT NULL,
    result VARCHAR(20) NOT NULL,
    operation_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    application_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    recovery_case_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    content_version_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    representation_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    authority_model_definition_sha256 CHAR(64) NOT NULL,
    definition_bundle_sha256 CHAR(64) NOT NULL,
    trace_bundle_artifact_id UUID NOT NULL REFERENCES working_paper_artifact(id) ON DELETE RESTRICT,
    trace_bundle_sha256 CHAR(64) NOT NULL,
    server_timeline_digest CHAR(64) NOT NULL,
    database_snapshot_digest CHAR(64) NOT NULL,
    browser_build VARCHAR(120) NOT NULL,
    error_code VARCHAR(60),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpees_scenario UNIQUE (run_id, scenario_id, ordinal),
    CONSTRAINT ck_wpees_ordinal_positive CHECK (ordinal >= 1),
    CONSTRAINT ck_wpees_result CHECK (result IN ('passed', 'failed', 'unverifiable')),
    CONSTRAINT ck_wpees_scenario_kind CHECK (scenario_kind IN (
        'standard', 'download_only', 'recovery_reject', 'recovery_claim', 'close_capture')),
    CONSTRAINT ck_wpees_authority_digest CHECK (wpsync_is_digest(authority_model_definition_sha256)),
    CONSTRAINT ck_wpees_bundle_digest CHECK (wpsync_is_digest(definition_bundle_sha256)),
    CONSTRAINT ck_wpees_trace_digest CHECK (wpsync_is_digest(trace_bundle_sha256)),
    CONSTRAINT ck_wpees_timeline_digest CHECK (wpsync_is_digest(server_timeline_digest)),
    CONSTRAINT ck_wpees_snapshot_digest CHECK (wpsync_is_digest(database_snapshot_digest)),
    CONSTRAINT ck_wpees_id_arrays_are_arrays CHECK (
        jsonb_typeof(operation_ids) = 'array' AND jsonb_typeof(application_ids) = 'array'
        AND jsonb_typeof(recovery_case_ids) = 'array' AND jsonb_typeof(content_version_ids) = 'array'
        AND jsonb_typeof(representation_ids) = 'array'),
    -- download-only / recovery-reject：operation 与 application 恒空，但必须有 recovery case
    CONSTRAINT ck_wpees_download_only_zero_entities CHECK (
        scenario_kind NOT IN ('download_only', 'recovery_reject')
        OR (jsonb_array_length(operation_ids) = 0
            AND jsonb_array_length(application_ids) = 0
            AND jsonb_array_length(recovery_case_ids) >= 1)),
    -- standard/recovery_claim/close_capture passed：必须有真实 operation + application
    CONSTRAINT ck_wpees_standard_requires_entities CHECK (
        scenario_kind IN ('download_only', 'recovery_reject')
        OR result <> 'passed'
        OR (jsonb_array_length(operation_ids) >= 1 AND jsonb_array_length(application_ids) >= 1)),
    -- recovery_claim 还必须绑定 recovery case
    CONSTRAINT ck_wpees_recovery_claim_requires_case CHECK (
        scenario_kind <> 'recovery_claim' OR result <> 'passed'
        OR jsonb_array_length(recovery_case_ids) >= 1)
);

CREATE INDEX IF NOT EXISTS idx_wpees_run ON working_paper_entry_evidence_scenario (run_id, ordinal);

COMMENT ON TABLE working_paper_entry_evidence_scenario IS
    'V151 逐 scenario evidence：不可变实体；download_only/recovery_reject 的 operation/application 恒空且必须有 recovery case，其余 passed 场景必须有真实 operation+application（Requirement 12.11 / Property 69）';

-- test run 与 scenario 均为不可变实体（结果只能一次写入；禁止事后替换）
CREATE OR REPLACE FUNCTION wpsync_check_test_run_immutable() RETURNS trigger AS $fn$
BEGIN
    IF NEW.entry_id IS DISTINCT FROM OLD.entry_id
       OR NEW.source_commit IS DISTINCT FROM OLD.source_commit
       OR NEW.manifest_source_digest IS DISTINCT FROM OLD.manifest_source_digest
       OR NEW.editability IS DISTINCT FROM OLD.editability
       OR NEW.room_model IS DISTINCT FROM OLD.room_model
       OR NEW.scenario_profile_digest IS DISTINCT FROM OLD.scenario_profile_digest
       OR NEW.required_scenario_set_digest IS DISTINCT FROM OLD.required_scenario_set_digest
       OR NEW.authority_model_definition_sha256 IS DISTINCT FROM OLD.authority_model_definition_sha256
       OR NEW.definition_bundle_sha256 IS DISTINCT FROM OLD.definition_bundle_sha256
       OR NEW.run_manifest_artifact_id IS DISTINCT FROM OLD.run_manifest_artifact_id
       OR NEW.run_manifest_sha256 IS DISTINCT FROM OLD.run_manifest_sha256
       OR NEW.started_at IS DISTINCT FROM OLD.started_at THEN
        RAISE EXCEPTION 'sync test run 的 profile/identity 列不可变（stale 只能新建 run） (id=%)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpstr_immutable
    BEFORE UPDATE ON working_paper_sync_test_run
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_test_run_immutable();

CREATE OR REPLACE FUNCTION wpsync_check_scenario_immutable() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION 'working_paper_entry_evidence_scenario 为不可变实体，禁止 UPDATE（重跑只能新建 run） (id=%)', OLD.id
        USING ERRCODE = 'check_violation';
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpees_immutable
    BEFORE UPDATE ON working_paper_entry_evidence_scenario
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_scenario_immutable();

-- scenario 的 bundle/authority 必须与所属 run 一致（禁止跨 run/entry 复制 evidence）
CREATE OR REPLACE FUNCTION wpsync_check_scenario_identity() RETURNS trigger AS $fn$
DECLARE
    v_run_authority text;
    v_run_bundle text;
BEGIN
    SELECT r.authority_model_definition_sha256, r.definition_bundle_sha256
      INTO v_run_authority, v_run_bundle
      FROM working_paper_sync_test_run r WHERE r.id = NEW.run_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'scenario % 引用不存在的 test run %', NEW.id, NEW.run_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_run_authority <> NEW.authority_model_definition_sha256
       OR v_run_bundle <> NEW.definition_bundle_sha256 THEN
        RAISE EXCEPTION 'scenario % 的 authority/bundle identity 与所属 run 不一致（禁止跨 run 复制 evidence）', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpees_identity
    BEFORE INSERT ON working_paper_entry_evidence_scenario
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_scenario_identity();

-- ═══════════════════════════════════════════════════════════════════════════
-- 24. append-only timeline 通用守卫（Requirement 13.5 / Property 68）
--     四条 timeline（operation / application / close-intent / recovery case）
--     一律禁止 UPDATE 与 DELETE：删中间 event、伪造 event、直接改 current state 都必须打红。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION wpsync_forbid_timeline_mutation() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION '% 是 append-only timeline，禁止 % （删除中间 event / 伪造 event / 改写既有 event 一律拒绝）',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'check_violation';
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpsoe_append_only
    BEFORE UPDATE OR DELETE ON working_paper_sync_operation_event
    FOR EACH ROW EXECUTE FUNCTION wpsync_forbid_timeline_mutation();

CREATE OR REPLACE TRIGGER trg_wpcae_append_only
    BEFORE UPDATE OR DELETE ON working_paper_content_application_event
    FOR EACH ROW EXECUTE FUNCTION wpsync_forbid_timeline_mutation();

CREATE OR REPLACE TRIGGER trg_wpocie_append_only
    BEFORE UPDATE OR DELETE ON working_paper_oo_close_intent_event
    FOR EACH ROW EXECUTE FUNCTION wpsync_forbid_timeline_mutation();

CREATE OR REPLACE TRIGGER trg_wpcrce_append_only
    BEFORE UPDATE OR DELETE ON working_paper_callback_recovery_case_event
    FOR EACH ROW EXECUTE FUNCTION wpsync_forbid_timeline_mutation();

-- ═══════════════════════════════════════════════════════════════════════════
-- 25. revision 0 回填台账（Task 9 硬判据："revision 0 回填台账"）
--     只引用项目现有事实、不写模板库、不改业务值、不创建 content version/artifact。
--     无法形成合法 approved bundle 的 entry 保持 single/unverified。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS working_paper_content_revision_backfill_ledger (
    wp_id UUID PRIMARY KEY REFERENCES working_paper(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    backfilled_content_revision BIGINT NOT NULL,
    legacy_file_version INTEGER,
    had_parsed_data BOOLEAN NOT NULL,
    entry_verification_state VARCHAR(20) NOT NULL DEFAULT 'unverified',
    content_version_created BOOLEAN NOT NULL DEFAULT false,
    representation_created BOOLEAN NOT NULL DEFAULT false,
    migration_version VARCHAR(10) NOT NULL DEFAULT '151',
    backfilled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 回填只能落 revision 0
    CONSTRAINT ck_wpcrbl_revision_zero CHECK (backfilled_content_revision = 0),
    -- 回填不得创建 content version / representation（否则等于伪造历史业务版本）
    CONSTRAINT ck_wpcrbl_no_entities CHECK (
        content_version_created = false AND representation_created = false),
    CONSTRAINT ck_wpcrbl_entry_state CHECK (entry_verification_state IN ('unverified', 'single', 'verified'))
);

CREATE INDEX IF NOT EXISTS idx_wpcrbl_project ON working_paper_content_revision_backfill_ledger (project_id);

COMMENT ON TABLE working_paper_content_revision_backfill_ledger IS
    'V151 revision 0 回填台账：逐 wp 记录 content_revision=0 起点与 legacy file_version 只读快照；回填不创建 content version/representation、不写模板库、不改业务值，entry 保持 unverified 直到形成合法 approved bundle';

-- 幂等回填：只对尚无台账记录的 wp 追加，不 UPDATE 任何业务列（content_revision 由 DEFAULT 0 提供）
INSERT INTO working_paper_content_revision_backfill_ledger
    (wp_id, project_id, backfilled_content_revision, legacy_file_version, had_parsed_data, entry_verification_state)
SELECT w.id, w.project_id, 0, w.file_version, (w.parsed_data IS NOT NULL), 'unverified'
  FROM working_paper w
 WHERE NOT EXISTS (
    SELECT 1 FROM working_paper_content_revision_backfill_ledger l WHERE l.wp_id = w.id
 );

-- 台账为 append-only 只读快照：禁止改写回填事实
CREATE OR REPLACE FUNCTION wpsync_check_backfill_ledger_immutable() RETURNS trigger AS $fn$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'revision 0 回填台账禁止删除 (wp_id=%)', OLD.wp_id
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.wp_id IS DISTINCT FROM OLD.wp_id
       OR NEW.project_id IS DISTINCT FROM OLD.project_id
       OR NEW.backfilled_content_revision IS DISTINCT FROM OLD.backfilled_content_revision
       OR NEW.legacy_file_version IS DISTINCT FROM OLD.legacy_file_version
       OR NEW.had_parsed_data IS DISTINCT FROM OLD.had_parsed_data
       OR NEW.migration_version IS DISTINCT FROM OLD.migration_version
       OR NEW.backfilled_at IS DISTINCT FROM OLD.backfilled_at THEN
        RAISE EXCEPTION 'revision 0 回填台账的回填事实不可变（只允许 entry_verification_state 推进） (wp_id=%)', OLD.wp_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wpcrbl_immutable
    BEFORE UPDATE OR DELETE ON working_paper_content_revision_backfill_ledger
    FOR EACH ROW EXECUTE FUNCTION wpsync_check_backfill_ledger_immutable();
