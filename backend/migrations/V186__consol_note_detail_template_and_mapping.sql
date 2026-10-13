-- V186: 合并附注明细模板与多企业行映射规则
-- spec: consol-note-detail-template-and-mapping Phase 1 Task 1
--
-- 5 张新表：
--   consol_note_detail_template          — 合并附注明细模板
--   consol_note_detail_template_version  — 模板不可变版本
--   consol_note_template_binding         — 项目绑定到版本
--   consol_note_mapping_rule             — 来源行→目标行转换规则
--   consol_note_mapping_binding          — 企业级规则绑定与 stale 状态

-- ─── 1. 合并附注明细模板 ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS consol_note_detail_template (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_type   VARCHAR(20)  NOT NULL,
    section_id      VARCHAR(64)  NOT NULL,
    name            VARCHAR(200) NOT NULL DEFAULT '',
    visibility      VARCHAR(20)  NOT NULL DEFAULT 'project',
    created_by      UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_deleted      BOOLEAN      NOT NULL DEFAULT false,
    CONSTRAINT ck_cndt_template_type CHECK (template_type IN ('soe', 'listed')),
    CONSTRAINT ck_cndt_visibility    CHECK (visibility IN ('draft', 'project', 'firm'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cndt_active
    ON consol_note_detail_template (template_type, section_id, created_by)
    WHERE is_deleted = false;

-- ─── 2. 模板不可变版本 ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS consol_note_detail_template_version (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id     UUID         NOT NULL REFERENCES consol_note_detail_template(id) ON DELETE CASCADE,
    version_number  INTEGER      NOT NULL,
    rows            JSONB        NOT NULL DEFAULT '[]'::jsonb,
    change_note     TEXT,
    created_by      UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_cndtv_version_positive CHECK (version_number > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cndtv_template_version
    ON consol_note_detail_template_version (template_id, version_number);

-- ─── 3. 项目绑定到版本 ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS consol_note_template_binding (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    section_id          VARCHAR(64)  NOT NULL,
    template_version_id UUID         NOT NULL REFERENCES consol_note_detail_template_version(id) ON DELETE RESTRICT,
    bound_by            UUID         REFERENCES users(id) ON DELETE SET NULL,
    bound_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cntb_project_section
    ON consol_note_template_binding (project_id, section_id);

-- ─── 4. 来源行→目标行转换规则 ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS consol_note_mapping_rule (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    section_id              VARCHAR(64)  NOT NULL,
    template_version_id     UUID         NOT NULL REFERENCES consol_note_detail_template_version(id) ON DELETE RESTRICT,
    source_structure_hash   VARCHAR(64)  NOT NULL,
    version_number          INTEGER      NOT NULL DEFAULT 1,
    mappings                JSONB        NOT NULL DEFAULT '[]'::jsonb,
    confirmed_by            UUID         REFERENCES users(id) ON DELETE SET NULL,
    confirmed_at            TIMESTAMPTZ,
    is_active               BOOLEAN      NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_cnmr_version_positive CHECK (version_number > 0),
    CONSTRAINT ck_cnmr_hash_length      CHECK (length(source_structure_hash) = 64)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cnmr_unique_rule
    ON consol_note_mapping_rule (project_id, section_id, template_version_id, source_structure_hash, version_number)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_cnmr_project_section
    ON consol_note_mapping_rule (project_id, section_id)
    WHERE is_active = true;

-- ─── 5. 企业级规则绑定 ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS consol_note_mapping_binding (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    section_id          VARCHAR(64)  NOT NULL,
    entity_node_key     VARCHAR(128) NOT NULL,
    entity_project_id   UUID         NOT NULL,
    rule_id             UUID         NOT NULL REFERENCES consol_note_mapping_rule(id) ON DELETE CASCADE,
    bound_source_hash   VARCHAR(64)  NOT NULL,
    status              VARCHAR(20)  NOT NULL DEFAULT 'confirmed',
    bound_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_cnmb_status       CHECK (status IN ('confirmed', 'stale', 'excluded')),
    CONSTRAINT ck_cnmb_hash_length  CHECK (length(bound_source_hash) = 64)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cnmb_project_section_entity
    ON consol_note_mapping_binding (project_id, section_id, entity_node_key);

CREATE INDEX IF NOT EXISTS idx_cnmb_rule
    ON consol_note_mapping_binding (rule_id);
