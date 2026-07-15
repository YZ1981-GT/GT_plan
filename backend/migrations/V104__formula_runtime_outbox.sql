-- V104: Formula Runtime — 运行批次扩展、快照扩展、wp_formula 生命周期字段、outbox 与并发约束
-- Requirements: Req 4 (事务快照), Req 8 (并发锁/指纹), Req 9 (事务模式)
-- Spec: formula-runtime-convergence Task 11

-- ============================================================
-- 1. draft_refresh_audit 扩展：revision_fingerprint / transaction_mode / idempotency_key / failure_detail
-- ============================================================

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'draft_refresh_audit' AND column_name = 'revision_fingerprint'
    ) THEN
        ALTER TABLE draft_refresh_audit ADD COLUMN revision_fingerprint VARCHAR(64);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'draft_refresh_audit' AND column_name = 'transaction_mode'
    ) THEN
        ALTER TABLE draft_refresh_audit ADD COLUMN transaction_mode VARCHAR(30) DEFAULT 'all_or_nothing';
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'draft_refresh_audit' AND column_name = 'idempotency_key'
    ) THEN
        ALTER TABLE draft_refresh_audit ADD COLUMN idempotency_key VARCHAR(64);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'draft_refresh_audit' AND column_name = 'failure_detail'
    ) THEN
        ALTER TABLE draft_refresh_audit ADD COLUMN failure_detail JSONB;
    END IF;
END $$;

-- 唯一约束: (project_id, year, idempotency_key) 防并发重复执行
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'uq_audit_project_year_idempotency'
    ) THEN
        CREATE UNIQUE INDEX uq_audit_project_year_idempotency
            ON draft_refresh_audit(project_id, year, idempotency_key)
            WHERE idempotency_key IS NOT NULL;
    END IF;
END $$;

-- ============================================================
-- 2. draft_refresh_snapshot 扩展：domain / target_locator / after_value / before_version / after_version / restored_at
-- ============================================================

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'draft_refresh_snapshot' AND column_name = 'domain'
    ) THEN
        ALTER TABLE draft_refresh_snapshot ADD COLUMN domain VARCHAR(30);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'draft_refresh_snapshot' AND column_name = 'target_locator'
    ) THEN
        ALTER TABLE draft_refresh_snapshot ADD COLUMN target_locator JSONB;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'draft_refresh_snapshot' AND column_name = 'after_value'
    ) THEN
        ALTER TABLE draft_refresh_snapshot ADD COLUMN after_value JSONB;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'draft_refresh_snapshot' AND column_name = 'before_version'
    ) THEN
        ALTER TABLE draft_refresh_snapshot ADD COLUMN before_version VARCHAR(64);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'draft_refresh_snapshot' AND column_name = 'after_version'
    ) THEN
        ALTER TABLE draft_refresh_snapshot ADD COLUMN after_version VARCHAR(64);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'draft_refresh_snapshot' AND column_name = 'restored_at'
    ) THEN
        ALTER TABLE draft_refresh_snapshot ADD COLUMN restored_at TIMESTAMPTZ;
    END IF;
END $$;

-- ============================================================
-- 3. wp_formula 扩展：lifecycle_state / definition_version / definition_hash
-- ============================================================

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'wp_formula' AND column_name = 'lifecycle_state'
    ) THEN
        ALTER TABLE wp_formula ADD COLUMN lifecycle_state VARCHAR(20) DEFAULT 'saved';
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'wp_formula' AND column_name = 'definition_version'
    ) THEN
        ALTER TABLE wp_formula ADD COLUMN definition_version INTEGER DEFAULT 1;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'wp_formula' AND column_name = 'definition_hash'
    ) THEN
        ALTER TABLE wp_formula ADD COLUMN definition_hash VARCHAR(64);
    END IF;
END $$;

-- ============================================================
-- 4. 新表 formula_runtime_outbox
-- ============================================================

CREATE TABLE IF NOT EXISTS formula_runtime_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_key VARCHAR(128) NOT NULL,
    run_id UUID NOT NULL REFERENCES draft_refresh_audit(id),
    event_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    attempts INTEGER NOT NULL DEFAULT 0,
    delivered_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- event_key UNIQUE constraint for idempotent publishing
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'uq_outbox_event_key'
    ) THEN
        CREATE UNIQUE INDEX uq_outbox_event_key ON formula_runtime_outbox(event_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_outbox_run_id ON formula_runtime_outbox(run_id);
CREATE INDEX IF NOT EXISTS idx_outbox_undelivered ON formula_runtime_outbox(delivered_at) WHERE delivered_at IS NULL;

COMMENT ON TABLE formula_runtime_outbox IS 'Formula runtime transactional outbox — 与业务写入同事务提交，提交后可靠发布 stale/invalidation 事件';
COMMENT ON COLUMN formula_runtime_outbox.event_key IS '幂等键 — publisher 使用 event_key 保证不重复发送';
COMMENT ON COLUMN formula_runtime_outbox.attempts IS '已尝试发布次数 — 失败时递增可重试';
