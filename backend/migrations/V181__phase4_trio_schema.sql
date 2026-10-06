-- V181：交付中心三件套 — 扩展 job/item + 新建 attempt/snapshot
--
-- spec: chain-closure-phase4-deliverable-center-trio 任务 3
-- 设计: §三（3.1 job / 3.2 item / 3.3 attempt / 3.4 snapshot）
--
-- 扩展 export_jobs_v2 / export_job_items_v2 加 trio 字段；
-- 新建 export_job_attempts（append-only 历史）和 deliverable_snapshots（不可变快照）。
-- 所有 DDL 幂等（IF NOT EXISTS / DO $$ ... $$）；回滚见 R181。

-- ====================================================================
-- 1. deliverable_snapshots — 不可变交付快照
-- ====================================================================

CREATE TABLE IF NOT EXISTS deliverable_snapshots (
    id              UUID          NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id      UUID          NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year            INTEGER       NOT NULL,
    digest          VARCHAR(64)   NOT NULL,
    payload         JSONB,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    created_by      UUID
);

-- digest 唯一约束（同一输入只有一份快照）
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_deliverable_snapshots_digest'
        AND connamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())
    ) THEN
        ALTER TABLE deliverable_snapshots
            ADD CONSTRAINT uq_deliverable_snapshots_digest UNIQUE (digest);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_deliverable_snapshots_project_year
    ON deliverable_snapshots (project_id, year);

-- ====================================================================
-- 2. export_jobs_v2 — 扩展 trio 字段
-- ====================================================================

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_jobs_v2' AND column_name = 'snapshot_id'
    ) THEN
        ALTER TABLE export_jobs_v2 ADD COLUMN snapshot_id UUID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_jobs_v2' AND column_name = 'kind'
    ) THEN
        ALTER TABLE export_jobs_v2 ADD COLUMN kind VARCHAR(50);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_jobs_v2' AND column_name = 'year'
    ) THEN
        ALTER TABLE export_jobs_v2 ADD COLUMN year INTEGER;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_jobs_v2' AND column_name = 'trio_total'
    ) THEN
        ALTER TABLE export_jobs_v2 ADD COLUMN trio_total INTEGER NOT NULL DEFAULT 3;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_jobs_v2' AND column_name = 'trio_succeeded'
    ) THEN
        ALTER TABLE export_jobs_v2 ADD COLUMN trio_succeeded INTEGER NOT NULL DEFAULT 0;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_jobs_v2' AND column_name = 'started_at'
    ) THEN
        ALTER TABLE export_jobs_v2 ADD COLUMN started_at TIMESTAMPTZ;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_jobs_v2' AND column_name = 'finished_at'
    ) THEN
        ALTER TABLE export_jobs_v2 ADD COLUMN finished_at TIMESTAMPTZ;
    END IF;
END $$;

-- ====================================================================
-- 3. export_job_items_v2 — 扩展 trio 字段
-- ====================================================================

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_job_items_v2' AND column_name = 'step_key'
    ) THEN
        ALTER TABLE export_job_items_v2 ADD COLUMN step_key VARCHAR(50);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_job_items_v2' AND column_name = 'sequence'
    ) THEN
        ALTER TABLE export_job_items_v2 ADD COLUMN sequence INTEGER;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_job_items_v2' AND column_name = 'snapshot_id'
    ) THEN
        ALTER TABLE export_job_items_v2 ADD COLUMN snapshot_id UUID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_job_items_v2' AND column_name = 'version_id'
    ) THEN
        ALTER TABLE export_job_items_v2 ADD COLUMN version_id UUID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_job_items_v2' AND column_name = 'file_path'
    ) THEN
        ALTER TABLE export_job_items_v2 ADD COLUMN file_path VARCHAR(500);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_job_items_v2' AND column_name = 'file_size'
    ) THEN
        ALTER TABLE export_job_items_v2 ADD COLUMN file_size BIGINT;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_job_items_v2' AND column_name = 'file_sha256'
    ) THEN
        ALTER TABLE export_job_items_v2 ADD COLUMN file_sha256 VARCHAR(64);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_job_items_v2' AND column_name = 'attempt_count'
    ) THEN
        ALTER TABLE export_job_items_v2 ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'export_job_items_v2' AND column_name = 'last_attempt_id'
    ) THEN
        ALTER TABLE export_job_items_v2 ADD COLUMN last_attempt_id UUID;
    END IF;
END $$;

-- ====================================================================
-- 4. export_job_attempts — 不可变 attempt 历史
-- ====================================================================

CREATE TABLE IF NOT EXISTS export_job_attempts (
    id                  UUID          NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    job_id              UUID          NOT NULL REFERENCES export_jobs_v2(id) ON DELETE CASCADE,
    item_id             UUID          NOT NULL REFERENCES export_job_items_v2(id) ON DELETE CASCADE,
    attempt_no          INTEGER       NOT NULL,
    status              VARCHAR(30)   NOT NULL DEFAULT 'running',
    started_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    snapshot_id         UUID,
    error_type          TEXT,
    error_message       TEXT,
    diagnostic_detail   TEXT,
    file_path           VARCHAR(500),
    file_size           BIGINT,
    file_sha256         VARCHAR(64),
    version_id          UUID,
    created_by          UUID,
    trigger_source      VARCHAR(30)
);

-- 同一 item 的 attempt_no 唯一递增
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_export_job_attempts_item_no'
        AND connamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())
    ) THEN
        ALTER TABLE export_job_attempts
            ADD CONSTRAINT uq_export_job_attempts_item_no
            UNIQUE (item_id, attempt_no);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_export_job_attempts_job
    ON export_job_attempts (job_id);

CREATE INDEX IF NOT EXISTS ix_export_job_attempts_item
    ON export_job_attempts (item_id, attempt_no);

COMMENT ON TABLE deliverable_snapshots IS
    '不可变交付快照（digest 不含生成时间和绝对路径）';
COMMENT ON TABLE export_job_attempts IS
    '后台导出任务 attempt 历史（append-only，失败记录不可覆盖）';
