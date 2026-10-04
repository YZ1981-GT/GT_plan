-- V180：交付中心三件套一键出具 — attempt append-only 历史 + 三层一致字段
-- spec chain-closure-phase4-deliverable-center-trio / Task 3（需求 1.5, 2.4, 3.2, 7.5）
--
-- 设计 §3：优先扩展现有 export_jobs_v2 / export_job_items_v2 / word_export_task_versions，
-- 并新增 export_job_attempts（append-only 失败历史）。
--
-- 全部 DDL 幂等（ADD COLUMN / CREATE TABLE / CREATE INDEX 均 IF NOT EXISTS），可重复执行；
-- 两次执行结果一致（PG 幂等由 Task 3 测试守护）。回滚见 R180。

-- ---------------------------------------------------------------------------
-- 1. export_jobs_v2（交付 job 扩展：固定三件套总数、成功计数、共享快照、readiness 摘要、时间点）
-- ---------------------------------------------------------------------------
ALTER TABLE export_jobs_v2 ADD COLUMN IF NOT EXISTS snapshot_id VARCHAR(64);
ALTER TABLE export_jobs_v2 ADD COLUMN IF NOT EXISTS trio_total INTEGER NOT NULL DEFAULT 3;
ALTER TABLE export_jobs_v2 ADD COLUMN IF NOT EXISTS trio_succeeded INTEGER NOT NULL DEFAULT 0;
ALTER TABLE export_jobs_v2 ADD COLUMN IF NOT EXISTS readiness JSONB;
ALTER TABLE export_jobs_v2 ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE export_jobs_v2 ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;

-- ---------------------------------------------------------------------------
-- 2. export_job_items_v2（明细项扩展：稳定 step_key + 固定 sequence + 共享快照 +
--    文件指纹投影 + attempt 投影 + 版本绑定）
-- ---------------------------------------------------------------------------
ALTER TABLE export_job_items_v2 ADD COLUMN IF NOT EXISTS step_key VARCHAR(50);
ALTER TABLE export_job_items_v2 ADD COLUMN IF NOT EXISTS sequence INTEGER;
ALTER TABLE export_job_items_v2 ADD COLUMN IF NOT EXISTS snapshot_id VARCHAR(64);
ALTER TABLE export_job_items_v2 ADD COLUMN IF NOT EXISTS version_id UUID;
ALTER TABLE export_job_items_v2 ADD COLUMN IF NOT EXISTS file_path TEXT;
ALTER TABLE export_job_items_v2 ADD COLUMN IF NOT EXISTS file_size BIGINT;
ALTER TABLE export_job_items_v2 ADD COLUMN IF NOT EXISTS file_sha256 VARCHAR(64);
ALTER TABLE export_job_items_v2 ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE export_job_items_v2 ADD COLUMN IF NOT EXISTS last_attempt_id UUID;

-- 同一 job 内一个 step_key 只应有一行（三件套固定 3 行）。NULL step_key（旧行/辅助项）
-- 不参与该约束。
CREATE UNIQUE INDEX IF NOT EXISTS uq_export_job_item_step
    ON export_job_items_v2 (job_id, step_key)
    WHERE step_key IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3. word_export_task_versions（版本行扩展：显式 file_sha256 命名列 + snapshot_id 直绑）
--    历史 file_hash 保留（DeliverableHashService 旁路写），新链路写 file_sha256。
-- ---------------------------------------------------------------------------
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS file_sha256 VARCHAR(64);
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS snapshot_id VARCHAR(64);

-- ---------------------------------------------------------------------------
-- 4. export_job_attempts（append-only 失败/重试历史；失败 attempt 永不覆盖）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS export_job_attempts (
    id              UUID         PRIMARY KEY,
    job_id          UUID         NOT NULL REFERENCES export_jobs_v2(id),
    item_id         UUID         NOT NULL REFERENCES export_job_items_v2(id),
    attempt_no      INTEGER      NOT NULL,
    status          VARCHAR(30)  NOT NULL DEFAULT 'running',
    trigger         VARCHAR(30),
    snapshot_id     VARCHAR(64),
    error_type      VARCHAR(120),
    error_message   TEXT,
    diagnostic_detail JSONB,
    file_path       TEXT,
    file_size       BIGINT,
    file_sha256     VARCHAR(64),
    version_id      UUID,
    created_by      UUID,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ
);

-- 同一 item 的 attempt_no 单调唯一（append-only，禁覆盖）。
CREATE UNIQUE INDEX IF NOT EXISTS uq_export_job_attempt_item_no
    ON export_job_attempts (item_id, attempt_no);

CREATE INDEX IF NOT EXISTS idx_export_job_attempts_job
    ON export_job_attempts (job_id, item_id);

COMMENT ON TABLE export_job_attempts IS
    '交付 job 的 append-only 尝试历史；失败 attempt 永不覆盖，重试只新增（phase4 Task 3）';
COMMENT ON COLUMN export_job_items_v2.step_key IS
    '稳定步骤键 financial_report/disclosure_notes/audit_report；辅助项用独立非 trio key';
COMMENT ON COLUMN export_jobs_v2.snapshot_id IS
    '三件套共享的不可变交付快照摘要；三项 item 必须引用同一值（phase4 需求 1.5/2.4）';
