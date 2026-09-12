-- V160: 行名对齐映射存储（formula-row-name-alignment-confirmation Task 7）
--
-- 名称对齐层的 N:M 映射持久化：底稿行名 ↔ 账套明细名（aux_name / account_name）。
-- 既有 workpaper_field_overrides（单 scope 单字段值 + UPSERT）无法承载：
--   ① 可 SQL 查询的多目标身份（判 stale / 多对一交集）
--   ② 版本 / 幂等 / 乐观锁列（批量确认原子性与冲突检测）
--   ③ superseded_from 留痕链（覆盖历史确认留痕）
--   ④ dataset 指纹（stale 回落）
-- 故新建本表（评估见 evidence/T01-storage-form-decision.md）。
--
-- 版本模型：每次确认写**新行**（mapping_version+1，is_active=true），旧行置
-- is_active=false 并被新行 superseded_from 指向 → 覆盖历史天然留痕、不原地改。
-- 作用域键 (project_id, year, wp_code, sheet_code, row_key) 的 active 版本唯一。

-- ── 主表：映射版本行 ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workpaper_row_name_mapping (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 作用域（Requirement 3.2）：稳定 row_key 来自模板/契约业务键，非行号/下标
    project_id UUID NOT NULL,
    year INT NOT NULL,
    wp_code VARCHAR(64) NOT NULL,
    sheet_code VARCHAR(128) NOT NULL,
    row_key VARCHAR(256) NOT NULL,

    -- 目标身份数组（展示 + 快照）；可查询明细见伴生表 *_target
    targets JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- 状态：落库映射恒为 user_confirmed（其余四态在运行时计算，不落库）
    match_state VARCHAR(32) NOT NULL DEFAULT 'user_confirmed',

    -- stale 判定指纹（Requirement 1.4 / Property 2）：dataset_id + 目标身份集 + schema digest
    dataset_fingerprint VARCHAR(128),

    -- 版本 / 幂等 / 乐观锁（Requirement 3.6）
    mapping_version INT NOT NULL DEFAULT 1,
    base_mapping_version INT,
    idempotency_key VARCHAR(128),

    -- 版本链与留痕（Requirement 3.5）
    is_active BOOLEAN NOT NULL DEFAULT true,
    superseded_from UUID REFERENCES workpaper_row_name_mapping(id),
    confirmed_by UUID REFERENCES users(id),
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- active 版本对作用域键唯一（部分唯一索引：仅约束 is_active 行，历史版本可共存）
CREATE UNIQUE INDEX IF NOT EXISTS uq_row_name_mapping_active_scope
    ON workpaper_row_name_mapping (project_id, year, wp_code, sheet_code, row_key)
    WHERE is_active;

-- 幂等键唯一（重复请求命中同一结果）；仅约束非空
CREATE UNIQUE INDEX IF NOT EXISTS uq_row_name_mapping_idempotency
    ON workpaper_row_name_mapping (project_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_row_name_mapping_scope
    ON workpaper_row_name_mapping (project_id, year, wp_code, sheet_code);

-- ── 伴生表：目标身份明细（让身份可 SQL 查询，判 stale / 多对一交集）──────────
-- 名称仅展示；判身份用 (account_code, aux_type, dimension_key, dataset_id, source_kind)。
CREATE TABLE IF NOT EXISTS workpaper_row_name_mapping_target (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mapping_id UUID NOT NULL REFERENCES workpaper_row_name_mapping(id) ON DELETE CASCADE,

    source_kind VARCHAR(16) NOT NULL,      -- aux_name | account_name
    account_code VARCHAR(64) NOT NULL,
    aux_type VARCHAR(64),
    aux_name VARCHAR(256) NOT NULL,        -- 展示名（不作身份判据）
    dimension_key VARCHAR(512) NOT NULL,   -- account_code|aux_type|归一名
    dataset_id UUID,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 按身份查询（多对一交集：同 dimension_key + dataset_id 被多个 mapping 引用）
CREATE INDEX IF NOT EXISTS ix_row_name_mapping_target_identity
    ON workpaper_row_name_mapping_target (dimension_key, dataset_id);

CREATE INDEX IF NOT EXISTS ix_row_name_mapping_target_mapping
    ON workpaper_row_name_mapping_target (mapping_id);
