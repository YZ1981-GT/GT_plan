-- V169: 公式推送引擎的目标级状态与运行记录（formula_push_state / formula_push_run）
--
-- 背景（spec chain-closure-phase2-formula-push-engine · 需求 2.6 / 3.2）：
--   四表入库、调整审批后，由公式推送引擎把试算表 / 四表 / 大厅已确认调整经公式内核
--   推送到底稿（E1 起步）与附注。可编辑目标要区分「引擎上次写的值」与「用户改过的值」，
--   才能做到「用户改过的不覆盖、没改过的跟着刷新」——既有表都承载不了这一判据：
--     * draft_marker 没有「上次推送值」列，三态判不了；
--     * draft_refresh_audit 的 operator_id NOT NULL，且同指纹第二次推送会被短路。
--   故新建两张表：
--     formula_push_state —— 每个推送目标一行（project, year, addr_id 唯一），
--                           记上次推送值 / 最近公式值 / 最近读到的当前值 / 三态；
--     formula_push_run   —— 每次运行一行，记触发来源、计数与逐项明细（面板「最近推送」）。
--
-- state 取值与 app/services/formula_push/policy.py 的 STATES 同源（测试钉死两侧一致）：
--   auto            引擎维护中（当前值 = 上次推送值 / 公式值）
--   manual          用户改过（当前 ≠ 上次推送值），不再覆盖，面板显示差异
--   locked          用户锁定，不再覆盖
--   pending_confirm 首次推送遇到来源不明的值且与公式值不等，等用户确认
--
-- 幂等：CREATE TABLE / INDEX 均 IF NOT EXISTS；重复执行安全。
-- 可回滚：见 R169（DROP TABLE）。两表均为新增，不改任何既有表。

CREATE TABLE IF NOT EXISTS formula_push_run (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       UUID         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year             INTEGER      NOT NULL,
    trigger_source   VARCHAR(40)  NOT NULL,   -- TRIAL_BALANCE_UPDATED / WORKPAPER_SAVED / manual
    triggered_by     UUID,                    -- 手动触发的用户；事件触发为 NULL
    status           VARCHAR(20)  NOT NULL DEFAULT 'running',
    written_count    INTEGER      NOT NULL DEFAULT 0,
    unchanged_count  INTEGER      NOT NULL DEFAULT 0,
    kept_count       INTEGER      NOT NULL DEFAULT 0,
    skipped_count    INTEGER      NOT NULL DEFAULT 0,
    detail           JSONB        NOT NULL DEFAULT '{}'::jsonb,
    started_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ,
    CONSTRAINT ck_formula_push_run_status
        CHECK (status IN ('running', 'succeeded', 'partial', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_formula_push_run_project_year
    ON formula_push_run (project_id, year, started_at);

COMMENT ON TABLE formula_push_run IS
    '公式推送引擎运行记录：每次运行一行（触发来源 / 写入·未变·保留·跳过计数 / 逐项明细）';

CREATE TABLE IF NOT EXISTS formula_push_state (
    id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID          NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year                INTEGER       NOT NULL,
    addr_id             VARCHAR(512)  NOT NULL,   -- 底稿域 E1/E1-1/<item_id>[<row_id>].<field>；附注域 note://...
    rule_id             VARCHAR(128)  NOT NULL,
    domain              VARCHAR(20)   NOT NULL,   -- workpaper / note
    wp_id               UUID          REFERENCES working_paper(id) ON DELETE CASCADE,
    note_section        VARCHAR(64),
    last_pushed_value   JSONB,                    -- 引擎上次实际写入（或确认等值）的值；NULL = 从未推送
    last_formula_value  JSONB,                    -- 最近一次求得的公式值（「采用公式值」用）
    current_value       JSONB,                    -- 最近一次读到的目标当前值
    state               VARCHAR(20)   NOT NULL DEFAULT 'auto',
    last_run_id         UUID          REFERENCES formula_push_run(id) ON DELETE SET NULL,
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_by          UUID,                     -- 最近一次采用 / 锁定的用户；引擎写入为 NULL
    CONSTRAINT uq_formula_push_state_addr UNIQUE (project_id, year, addr_id),
    CONSTRAINT ck_formula_push_state_state
        CHECK (state IN ('auto', 'manual', 'locked', 'pending_confirm')),
    CONSTRAINT ck_formula_push_state_domain
        CHECK (domain IN ('workpaper', 'note'))
);

CREATE INDEX IF NOT EXISTS idx_formula_push_state_project_year_state
    ON formula_push_state (project_id, year, state);

COMMENT ON TABLE formula_push_state IS
    '公式推送目标级状态：上次推送值 / 最近公式值 / 当前值 / 三态（auto·manual·locked·pending_confirm）';
COMMENT ON COLUMN formula_push_state.last_pushed_value IS
    '引擎上次写入（或判定等值采纳）的值；当前值 ≠ 本列 ⇒ 用户改过（manual），不再覆盖';
