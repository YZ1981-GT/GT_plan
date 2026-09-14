-- V100: 公式管理库（Formula Management Library）
--
-- 扩展 wp_formula（V052）为统一公式治理层：三类型（auto_calc / logic_check /
-- reasonability）+ 最近计算时间 + 规范化引用 + 初稿语义标记；新建 draft_marker /
-- draft_refresh_audit / draft_refresh_snapshot 三张配套表。
--
-- 幂等铁律：所有列补齐用 DO $$ + information_schema.columns 检测列存在性再 ALTER，
-- 所有表用 CREATE TABLE IF NOT EXISTS，所有索引用 CREATE INDEX IF NOT EXISTS，
-- 确保重复运行不报错（避免旧表列不同导致索引报错）。

-- ① 扩展 wp_formula：三类型 + 最近计算时间 + 引用规范化 + 问题描述 + 提示文案
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='wp_formula' AND column_name='formula_type') THEN
    ALTER TABLE wp_formula ADD COLUMN formula_type VARCHAR(20) NOT NULL DEFAULT 'auto_calc';
    -- formula_type ∈ {auto_calc, logic_check, reasonability}
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='wp_formula' AND column_name='last_computed_at') THEN
    ALTER TABLE wp_formula ADD COLUMN last_computed_at TIMESTAMPTZ NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='wp_formula' AND column_name='refs') THEN
    ALTER TABLE wp_formula ADD COLUMN refs JSONB NOT NULL DEFAULT '[]'::jsonb;
    -- refs: [{addr_id | formula_ref, ...}] —— 规范化引用，禁裸字符串
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='wp_formula' AND column_name='issue_description') THEN
    ALTER TABLE wp_formula ADD COLUMN issue_description TEXT NULL;   -- logic_check 问题描述
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='wp_formula' AND column_name='hint_text') THEN
    ALTER TABLE wp_formula ADD COLUMN hint_text TEXT NULL;           -- reasonability 提示文案
  END IF;
END $$;

-- ①（续）公式来源维度 + 参照链（Req 22）
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='wp_formula' AND column_name='formula_source') THEN
    ALTER TABLE wp_formula ADD COLUMN formula_source VARCHAR(20) NOT NULL DEFAULT 'custom';
    -- formula_source ∈ {preset, custom, reference}
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='wp_formula' AND column_name='reference_formula_id') THEN
    ALTER TABLE wp_formula ADD COLUMN reference_formula_id UUID NULL;
    -- reference 来源指向被参照源公式；非 reference 来源为 NULL
  END IF;
END $$;

-- ② 初稿标记：可查询、可区分初稿 vs 已审定
CREATE TABLE IF NOT EXISTS draft_marker (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL,
  year          INTEGER NOT NULL,
  unit_scope    VARCHAR(255) NOT NULL,   -- 数据单元定位（如 audit_sheet:{wp_id}:{cell} / report:{row_code}）
  state         VARCHAR(20) NOT NULL DEFAULT 'draft',  -- draft | human_edited
  refresh_id    UUID NULL,               -- 关联生成它的刷新批次
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_draft_marker_unit
  ON draft_marker (project_id, year, unit_scope);

-- ③ 审计留痕（append-only，不可篡改：仅 append，不暴露 UPDATE/DELETE 端点）
CREATE TABLE IF NOT EXISTS draft_refresh_audit (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID NOT NULL,
  year              INTEGER NOT NULL,
  operator_id       UUID NOT NULL,       -- 操作者身份
  operator_role     VARCHAR(50) NOT NULL,
  operated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  scope             VARCHAR(100) NOT NULL,  -- 触发范围
  tb_snapshot_hash  VARCHAR(64) NOT NULL,   -- 幂等键
  affected_count    INTEGER NOT NULL DEFAULT 0,  -- 受影响记录数
  result_status     VARCHAR(20) NOT NULL,   -- success | blocked | rolled_back
  detail            JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_draft_audit_project_year
  ON draft_refresh_audit (project_id, year, operated_at DESC);

-- ④ 回滚快照（覆盖前内容，供回滚恢复；FK → draft_refresh_audit）
CREATE TABLE IF NOT EXISTS draft_refresh_snapshot (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  refresh_id    UUID NOT NULL REFERENCES draft_refresh_audit(id),
  unit_scope    VARCHAR(255) NOT NULL,
  before_value  JSONB NOT NULL,          -- 覆盖前内容（供回滚恢复）
  editor_id     UUID NULL,               -- 被覆盖的人工编辑者标识（Req 4.3）
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_draft_snapshot_refresh
  ON draft_refresh_snapshot (refresh_id);
