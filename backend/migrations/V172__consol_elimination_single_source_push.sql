-- V172: 合并抵销分录单源与差额表推送（spec consol-elimination-single-source-push）
--
-- 1. elimination_entries.origin / origin_key —— 分录来源与来源内确定性键
--    origin NULL = 手工录入；ws_equity_sim / ws_internal_arap / ws_internal_trade = 由合并工作底稿生成的草稿；
--    legacy_sheet = 旧版「合并抵消分录明细表」JSON 自定义行转入。
--    (project_id, year, origin, origin_key) 部分唯一：重复生成按来源键更新同一笔分录（幂等），不重复入账。
--
-- 2. consol_push_run —— 合并推送运行记录（公式管理「合并推送」页）
--    每次推送一行：触发来源、状态、逐项目逐步骤结果、警告。
--
-- 3. consol_note_formula —— 合并附注单元格取数公式（模板级，按 soe / listed 区分）
--    (template_type, section_id, row_index, col_index) 部分唯一；source = seed（自动种子）/ manual（人工）。
--
-- 4. consol_note_data.is_stale —— 推送后置真，「按公式填入」后清除。
--
-- 存量安全：新增列均可空或有默认值；新表不改既有数据。
-- 幂等：ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS。
-- 可回滚：见 R172。

-- ── 1. elimination_entries 来源 ───────────────────────────────────────────────
ALTER TABLE elimination_entries ADD COLUMN IF NOT EXISTS origin VARCHAR(40);
ALTER TABLE elimination_entries ADD COLUMN IF NOT EXISTS origin_key VARCHAR(200);

CREATE UNIQUE INDEX IF NOT EXISTS ux_elim_entries_origin
    ON elimination_entries (project_id, year, origin, origin_key)
    WHERE is_deleted = false AND origin_key IS NOT NULL;

COMMENT ON COLUMN elimination_entries.origin IS
  '分录来源：NULL=手工；ws_equity_sim / ws_internal_arap / ws_internal_trade=合并工作底稿生成；legacy_sheet=旧版明细表转入';
COMMENT ON COLUMN elimination_entries.origin_key IS
  '来源内确定性键（同来源同键只对应一笔未删分录，重复生成按此更新草稿）';

-- ── 2. consol_push_run ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS consol_push_run (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year            INTEGER      NOT NULL,
    trigger_source  VARCHAR(40)  NOT NULL,   -- elimination_approved / elimination_revoked / formula_changed / manual
    triggered_by    UUID,                    -- 手动触发的用户；事件触发为 NULL
    status          VARCHAR(20)  NOT NULL DEFAULT 'running',
    steps           JSONB        NOT NULL DEFAULT '[]'::jsonb,   -- [{project_id, project_name, step, status, detail}]
    warnings        JSONB        NOT NULL DEFAULT '[]'::jsonb,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    CONSTRAINT ck_consol_push_run_status
        CHECK (status IN ('running', 'succeeded', 'partial', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_consol_push_run_project_year
    ON consol_push_run (project_id, year, started_at);

COMMENT ON TABLE consol_push_run IS
  '合并推送运行记录：分录审批 / 撤销审批 / 公式变更 / 手动触发后，重算差额表 → 合并试算 → 合并报表 → 标记附注待更新';

-- ── 3. consol_note_formula ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS consol_note_formula (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    template_type   VARCHAR(20)  NOT NULL,   -- soe / listed
    section_id      VARCHAR(64)  NOT NULL,   -- 合并附注表 id（如 五-5-1）
    row_index       INTEGER      NOT NULL,
    col_index       INTEGER      NOT NULL,
    formula         TEXT         NOT NULL,
    source          VARCHAR(20)  NOT NULL DEFAULT 'manual',
    description     TEXT,
    is_deleted      BOOLEAN      NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by      UUID,
    CONSTRAINT ck_consol_note_formula_source CHECK (source IN ('seed', 'manual')),
    CONSTRAINT ck_consol_note_formula_template CHECK (template_type IN ('soe', 'listed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_consol_note_formula_cell
    ON consol_note_formula (template_type, section_id, row_index, col_index)
    WHERE is_deleted = false;

COMMENT ON TABLE consol_note_formula IS
  '合并附注单元格取数公式（语法同报表公式 TB/SUM_TB/REPORT/ROW）；seed=自动种子、manual=人工维护';

-- ── 4. consol_note_data.is_stale ──────────────────────────────────────────────
ALTER TABLE consol_note_data ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN consol_note_data.is_stale IS
  '合并推送后置真（合并数已变化，附注数据待更新）；「按公式填入」后清除';
