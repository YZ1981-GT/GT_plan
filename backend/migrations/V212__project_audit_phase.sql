-- V212: 项目当前审计阶段与预审截止日 + 预审样本存续核对汇总表
--       （号码：实施时现扫 V211 已被并发会话的 attachment_ocr_confirmation 占用并落库，本迁移取 V212）
--       （spec voucher-identity-writeback-and-audit-phase 任务 8，ADR-VK-09 / ADR-VK-11，design §8 后半）
--
-- ── 为什么 ──────────────────────────────────────────────────────────────────
-- 「预审 / 年审」此前只存在于抽凭引擎的 prop：宿主各写各的字面量（多数写死 final，G5 / K1 / J1 /
-- M1 / M2 还拿它当「本期 / 期后」用），挂凭与回拉生成的行没有阶段。阶段是项目的事实，放项目上：
--   · current_audit_phase：preliminary 预审 / final 年审，缺省年审（与改造前多数宿主写死的值一致）；
--   · interim_cutoff_date：预审截止日（年审口径 a「只抽剩余期间」从它的次日起算）。
--   不放 JSONB：要在 SQL 里过滤，且要迁移 + ORM + schema 三层一致。
-- interim_survival_checks：账套重导后预审样本存续核对的汇总（任务 17 写入）。行在
-- checklist_responses 里由各宿主自管，后端读不到行结构，只落每底稿每账套版本一行的计数。
--
-- 存量：projects 全部回填为 final（缺省值），与改造前行为一致；新表为空。
-- 幂等：ADD COLUMN IF NOT EXISTS；约束按名判重；CREATE TABLE / INDEX IF NOT EXISTS。
-- 注：MigrationRunner 只在后端启动时跑（热重载不跑），应用本迁移需重启后端或手动 run_pending。

ALTER TABLE projects ADD COLUMN IF NOT EXISTS current_audit_phase varchar(16) NOT NULL DEFAULT 'final';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS interim_cutoff_date date;

COMMENT ON COLUMN projects.current_audit_phase IS
  '当前审计阶段：preliminary 预审 / final 年审（缺省）。抽凭、挂凭、挂凭回拉生成的行按它标阶段；'
  '经理、合伙人（含签字合伙人）、admin 可改，改动写 app_audit_log';
COMMENT ON COLUMN projects.interim_cutoff_date IS
  '预审截止日；年审口径 a（只抽剩余期间）的抽样框从它的次日起算';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_projects_current_audit_phase'
          AND conrelid = 'projects'::regclass
    ) THEN
        ALTER TABLE projects ADD CONSTRAINT ck_projects_current_audit_phase
            CHECK (current_audit_phase IN ('preliminary', 'final'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS interim_survival_checks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id),
    working_paper_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    total integer NOT NULL,
    unchanged integer NOT NULL,
    changed integer NOT NULL,
    deleted integer NOT NULL,
    renumbered integer NOT NULL,
    unacked integer NOT NULL,
    checked_by uuid,
    checked_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_interim_survival_checks_wp_dataset UNIQUE (working_paper_id, dataset_id)
);

CREATE INDEX IF NOT EXISTS idx_interim_survival_checks_project
    ON interim_survival_checks (project_id);

COMMENT ON TABLE interim_survival_checks IS
  '预审样本存续核对汇总：每底稿每账套版本一行（upsert）。四种状态计数 + 未确认的非「未变」行数；'
  '逐行状态在宿主行元数据 _gt.sv 里';
