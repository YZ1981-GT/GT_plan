-- V200: 合并附注映射规则复用与标准科目参考下推
-- spec: consol-note-mapping-reuse-and-reference-push

-- ═══════════════════════════════════════════════════════════════
-- 1. 映射规则模板库
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS consol_note_mapping_rule_template (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_type         VARCHAR(20)  NOT NULL,
    section_id            VARCHAR(64)  NOT NULL,
    source_structure_hash VARCHAR(64)  NOT NULL,
    version_number        INT          NOT NULL DEFAULT 1,
    mappings              JSONB        NOT NULL DEFAULT '[]',
    account_code_hints    JSONB                 DEFAULT '{}',
    source_project_id     UUID,
    source_rule_id        UUID,
    promoted_by           UUID         REFERENCES users(id) ON DELETE SET NULL,
    promoted_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_active             BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_cnmrt_template_type   CHECK (template_type IN ('soe', 'listed')),
    CONSTRAINT ck_cnmrt_hash_length     CHECK (length(source_structure_hash) = 64),
    CONSTRAINT ck_cnmrt_version_positive CHECK (version_number > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cnmrt_active_rule
    ON consol_note_mapping_rule_template (
        template_type, section_id, source_structure_hash, version_number
    ) WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_cnmrt_section
    ON consol_note_mapping_rule_template (template_type, section_id)
    WHERE is_active = TRUE;

-- ═══════════════════════════════════════════════════════════════
-- 2. 结构锁
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS consol_note_structure_lock (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consol_project_id UUID         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    section_id        VARCHAR(64)  NOT NULL,
    locked_version_id UUID         NOT NULL
        REFERENCES consol_note_detail_template_version(id) ON DELETE RESTRICT,
    lock_scope        VARCHAR(20)  NOT NULL DEFAULT 'rows_only',
    locked_by         UUID         REFERENCES users(id) ON DELETE SET NULL,
    locked_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_cnsl_scope CHECK (lock_scope IN ('rows_only', 'full'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cnsl_project_section
    ON consol_note_structure_lock (consol_project_id, section_id)
    WHERE is_active = TRUE;

-- 子企业锁定关联表（避免 check 时每次 build_tree）
CREATE TABLE IF NOT EXISTS consol_note_structure_lock_entity (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lock_id           UUID         NOT NULL
        REFERENCES consol_note_structure_lock(id) ON DELETE CASCADE,
    entity_project_id UUID         NOT NULL,
    entity_node_key   VARCHAR(128) NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cnsle_lock_entity
    ON consol_note_structure_lock_entity (lock_id, entity_project_id);

CREATE INDEX IF NOT EXISTS idx_cnsle_entity_project
    ON consol_note_structure_lock_entity (entity_project_id);

-- ═══════════════════════════════════════════════════════════════
-- 3. 值确认
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS consol_note_value_confirmation (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id           UUID         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    section_id           VARCHAR(64)  NOT NULL,
    entity_node_key      VARCHAR(128) NOT NULL DEFAULT '_self',
    confirmed_value_hash VARCHAR(64)  NOT NULL,
    confirmed_by         UUID         REFERENCES users(id) ON DELETE SET NULL,
    confirmed_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    status               VARCHAR(20)  NOT NULL DEFAULT 'confirmed',
    CONSTRAINT ck_cnvc_status      CHECK (status IN ('confirmed', 'outdated')),
    CONSTRAINT ck_cnvc_hash_length CHECK (length(confirmed_value_hash) = 64)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cnvc_project_section_entity
    ON consol_note_value_confirmation (project_id, section_id, entity_node_key);

CREATE INDEX IF NOT EXISTS idx_cnvc_project_status
    ON consol_note_value_confirmation (project_id, status);

-- ═══════════════════════════════════════════════════════════════
-- 4. 现有表扩展：consol_note_mapping_rule 新增提升溯源列
-- ═══════════════════════════════════════════════════════════════

ALTER TABLE consol_note_mapping_rule
    ADD COLUMN IF NOT EXISTS promoted_to_template_id UUID
        REFERENCES consol_note_mapping_rule_template(id) ON DELETE SET NULL;
