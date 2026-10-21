-- V199: 公式全局设置 / 本项目适配 / 公式模板（spec formula-global-settings-sync）
--
-- 有效定义 = 本项目适配 → 订阅的公式模板 → 全局设置 → 系统预设（取第一个存在的）。
-- 报表域两层继续放 report_config（准则行 = 全局，project:{id} 行 = 本项目适配），只加版本与基线列。
-- 其余域（试算表明细 / 表间审核 / 底稿 / 附注 / 合并附注）与全部模板层放 formula_setting。
-- 基线 = 本项目适配所依据的上游（全局或模板）定义快照与版本，用于三方比对判断「项目改过没有」。

-- ── 报表配置：全局行版本号 + 项目行基线 ──
ALTER TABLE report_config ADD COLUMN IF NOT EXISTS formula_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE report_config ADD COLUMN IF NOT EXISTS base_version INTEGER;
ALTER TABLE report_config ADD COLUMN IF NOT EXISTS base_definition JSONB;
ALTER TABLE report_config ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE report_config ADD COLUMN IF NOT EXISTS base_origin VARCHAR(16);
ALTER TABLE report_config ADD COLUMN IF NOT EXISTS base_template_id UUID;

-- ── 底稿公式：自定义行即底稿域的本项目适配 ──
ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS base_version INTEGER;
ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS base_definition JSONB;
ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS base_origin VARCHAR(16);
ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS base_template_id UUID;

-- ── 合并附注公式：模板级表即合并附注域的全局层 ──
ALTER TABLE consol_note_formula ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

-- ── 公式模板 ──
CREATE TABLE IF NOT EXISTS formula_template (
    id UUID PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    share_scope VARCHAR(16) NOT NULL DEFAULT 'personal',
    owner_user_id UUID REFERENCES users(id),
    owner_project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    applicable_scope VARCHAR(40) NOT NULL DEFAULT '',
    domains JSONB NOT NULL DEFAULT '[]'::jsonb,
    version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    created_by UUID,
    updated_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_formula_template_share_scope CHECK (share_scope IN ('personal', 'team', 'group', 'firm')),
    CONSTRAINT ck_formula_template_status CHECK (status IN ('active', 'archived')),
    CONSTRAINT ck_formula_template_owner_project CHECK (
        share_scope NOT IN ('team', 'group') OR owner_project_id IS NOT NULL
    )
);
CREATE INDEX IF NOT EXISTS ix_formula_template_owner ON formula_template (owner_user_id);
CREATE INDEX IF NOT EXISTS ix_formula_template_project ON formula_template (owner_project_id);

CREATE TABLE IF NOT EXISTS formula_template_version (
    id UUID PRIMARY KEY,
    template_id UUID NOT NULL REFERENCES formula_template(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    change_set JSONB NOT NULL DEFAULT '[]'::jsonb,
    note TEXT,
    published_by UUID,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_formula_template_version UNIQUE (template_id, version)
);

-- ── 统一公式设置（全局层 / 本项目层 / 模板层）──
CREATE TABLE IF NOT EXISTS formula_setting (
    id UUID PRIMARY KEY,
    domain VARCHAR(32) NOT NULL,
    layer VARCHAR(16) NOT NULL,
    scope VARCHAR(40) NOT NULL DEFAULT '',
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    template_id UUID REFERENCES formula_template(id) ON DELETE CASCADE,
    slot_key TEXT NOT NULL,
    slot_label TEXT,
    definition JSONB NOT NULL DEFAULT '{}'::jsonb,
    definition_hash VARCHAR(64),
    version INTEGER NOT NULL DEFAULT 1,
    base_version INTEGER,
    base_definition JSONB,
    pinned BOOLEAN NOT NULL DEFAULT false,
    base_origin VARCHAR(16),
    base_template_id UUID,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    created_by UUID,
    updated_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_formula_setting_layer CHECK (layer IN ('global', 'project', 'template')),
    CONSTRAINT ck_formula_setting_owner CHECK (
        (layer = 'global' AND project_id IS NULL AND template_id IS NULL)
        OR (layer = 'project' AND project_id IS NOT NULL AND template_id IS NULL)
        OR (layer = 'template' AND template_id IS NOT NULL AND project_id IS NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_formula_setting_global
    ON formula_setting (domain, scope, slot_key) WHERE layer = 'global' AND is_deleted = false;
CREATE UNIQUE INDEX IF NOT EXISTS uq_formula_setting_project
    ON formula_setting (domain, project_id, slot_key) WHERE layer = 'project' AND is_deleted = false;
CREATE UNIQUE INDEX IF NOT EXISTS uq_formula_setting_template
    ON formula_setting (domain, template_id, slot_key) WHERE layer = 'template' AND is_deleted = false;
CREATE INDEX IF NOT EXISTS ix_formula_setting_project ON formula_setting (project_id, domain);

-- ── 待确认事项（冲突 / 管理员暂缓）──
CREATE TABLE IF NOT EXISTS formula_sync_item (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    domain VARCHAR(32) NOT NULL,
    slot_key TEXT NOT NULL,
    slot_label TEXT,
    reason VARCHAR(16) NOT NULL,
    upstream_origin VARCHAR(16) NOT NULL DEFAULT 'global',
    upstream_template_id UUID,
    base_definition JSONB,
    upstream_definition JSONB,
    local_definition JSONB,
    upstream_version INTEGER,
    publish_id UUID,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    resolution VARCHAR(16),
    resolved_definition JSONB,
    resolved_by UUID,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_formula_sync_item_reason CHECK (reason IN ('conflict', 'deferred')),
    CONSTRAINT ck_formula_sync_item_status CHECK (status IN ('pending', 'resolved', 'superseded')),
    CONSTRAINT ck_formula_sync_item_resolution CHECK (resolution IS NULL OR resolution IN ('adopt', 'keep', 'custom'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_formula_sync_item_pending
    ON formula_sync_item (project_id, domain, slot_key) WHERE status = 'pending';

-- ── 发布记录（全局发布 / 模板发布 / 应用到项目 / 全局候选）──
CREATE TABLE IF NOT EXISTS formula_publish (
    id UUID PRIMARY KEY,
    domain VARCHAR(32) NOT NULL,
    scope VARCHAR(40) NOT NULL DEFAULT '',
    target VARCHAR(16) NOT NULL DEFAULT 'global',
    template_id UUID,
    source VARCHAR(24) NOT NULL,
    source_project_id UUID,
    request_id VARCHAR(64),
    status VARCHAR(16) NOT NULL DEFAULT 'published',
    change_set JSONB NOT NULL DEFAULT '[]'::jsonb,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    note TEXT,
    published_by UUID,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,
    CONSTRAINT ck_formula_publish_target CHECK (target IN ('global', 'template', 'projects')),
    CONSTRAINT ck_formula_publish_status CHECK (status IN ('published', 'pending', 'rejected'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_formula_publish_request
    ON formula_publish (request_id) WHERE request_id IS NOT NULL;

-- ── 模板订阅（每个项目每个域最多一个有效订阅）──
CREATE TABLE IF NOT EXISTS formula_template_subscription (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    domain VARCHAR(32) NOT NULL,
    template_id UUID NOT NULL REFERENCES formula_template(id),
    template_version INTEGER NOT NULL,
    pinned BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    subscribed_by UUID,
    subscribed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    unsubscribed_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_formula_template_subscription_active
    ON formula_template_subscription (project_id, domain) WHERE is_active = true;

-- ── 回填：已有的报表项目行以对应准则行为基线（版本 1）──
-- 准则码与 ReportConfigService.resolve_applicable_standard 同口径（模板类型缺省 soe、范围缺省 standalone）。
UPDATE report_config AS p
SET base_version = g.formula_version,
    base_origin = 'global',
    base_definition = jsonb_build_object(
        'formula', COALESCE(g.formula, ''),
        'aje_formula', COALESCE(g.aje_formula, ''),
        'rje_formula', COALESCE(g.rje_formula, ''),
        'formula_category', COALESCE(g.formula_category, ''),
        'formula_description', COALESCE(g.formula_description, ''),
        'formula_source', COALESCE(g.formula_source, '')
    )
FROM projects AS pr, report_config AS g
WHERE p.applicable_standard LIKE 'project:%'
  AND p.base_version IS NULL
  AND p.is_deleted = false
  AND pr.id::text = substring(p.applicable_standard FROM 9)
  AND g.applicable_standard = COALESCE(pr.template_type, 'soe') || '_' || COALESCE(pr.report_scope, 'standalone')
  AND g.report_type = p.report_type
  AND g.row_code = p.row_code
  AND g.is_deleted = false;

-- ── 迁入旧存储：试算表科目明细公式（projects.wizard_state.tb_detail_formulas）→ 本项目层 ──
-- 公式位：覆盖项 = 科目编码，新增行 = added:行编码。旧 wizard_state 原样保留（回滚后旧代码仍可读）。
INSERT INTO formula_setting (id, domain, layer, scope, project_id, slot_key, slot_label, definition, version)
SELECT gen_random_uuid(), 'tb_detail', 'project', '', p.id, o.key, COALESCE(NULLIF(o.value->>'row_name', ''), o.key),
       jsonb_build_object(
           'row_name', o.value->>'row_name',
           'formula', o.value->>'formula',
           'formula_category', COALESCE(NULLIF(o.value->>'formula_category', ''), 'auto_calc'),
           'formula_description', o.value->>'formula_description'),
       1
FROM projects AS p
CROSS JOIN LATERAL jsonb_each(CASE WHEN jsonb_typeof(p.wizard_state->'tb_detail_formulas'->'overrides') = 'object'
                                   THEN p.wizard_state->'tb_detail_formulas'->'overrides'
                                   ELSE '{}'::jsonb END) AS o
WHERE jsonb_typeof(o.value) = 'object'
ON CONFLICT DO NOTHING;

INSERT INTO formula_setting (id, domain, layer, scope, project_id, slot_key, slot_label, definition, version)
SELECT gen_random_uuid(), 'tb_detail', 'project', '', p.id, 'added:' || (a.value->>'row_code'),
       COALESCE(NULLIF(a.value->>'row_name', ''), a.value->>'row_code'),
       jsonb_build_object(
           'row_name', a.value->>'row_name',
           'formula', a.value->>'formula',
           'formula_category', COALESCE(NULLIF(a.value->>'formula_category', ''), 'auto_calc'),
           'formula_description', a.value->>'formula_description'),
       1
FROM projects AS p
CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(p.wizard_state->'tb_detail_formulas'->'added') = 'array'
                                             THEN p.wizard_state->'tb_detail_formulas'->'added'
                                             ELSE '[]'::jsonb END) AS a
WHERE jsonb_typeof(a.value) = 'object'
  AND COALESCE(a.value->>'row_code', '') <> ''
ON CONFLICT DO NOTHING;

-- ── 迁入旧存储：表间审核用户规则（projects.wizard_state.cross_check_user_rules）→ 本项目层 ──
-- 公式位：{树节点 key}#0{4 位序号}（保持原顺序，且排在新规则之前：新规则编号以十六进制毫秒时间戳开头，首位为 1）。
INSERT INTO formula_setting (id, domain, layer, scope, project_id, slot_key, slot_label, definition, version)
SELECT gen_random_uuid(), 'cross_check', 'project', '', p.id,
       n.key || '#0' || lpad((r.ord - 1)::text, 4, '0'),
       COALESCE(NULLIF(r.value->>'label', ''), n.key),
       jsonb_build_object(
           'label', r.value->>'label',
           'left_ref', r.value->>'left_ref',
           'operator', COALESCE(NULLIF(r.value->>'operator', ''), '='),
           'right_ref', r.value->>'right_ref',
           'description', r.value->>'description',
           'tolerance', r.value->'tolerance'),
       1
FROM projects AS p
CROSS JOIN LATERAL jsonb_each(CASE WHEN jsonb_typeof(p.wizard_state->'cross_check_user_rules') = 'object'
                                   THEN p.wizard_state->'cross_check_user_rules'
                                   ELSE '{}'::jsonb END) AS n
CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(n.value) = 'array'
                                             THEN n.value ELSE '[]'::jsonb END) WITH ORDINALITY AS r(value, ord)
WHERE jsonb_typeof(r.value) = 'object'
  AND position('#' in n.key) = 0
ON CONFLICT DO NOTHING;
