-- V238: 耐久 AI 批任务与逐项租约

CREATE TABLE IF NOT EXISTS ai_task_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    task_kind VARCHAR(40) NOT NULL,
    actor_id UUID NOT NULL REFERENCES users(id),
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(24) NOT NULL DEFAULT 'queued',
    cancel_requested_at TIMESTAMPTZ,
    progress_total INTEGER NOT NULL DEFAULT 0,
    progress_done INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    cancelled_count INTEGER NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ai_task_job_kind CHECK (task_kind IN ('note_batch_prefill','workpaper_batch_review')),
    CONSTRAINT ck_ai_task_job_status CHECK (status IN ('queued','running','succeeded','partial_failed','failed','cancelling','cancelled')),
    CONSTRAINT ck_ai_task_job_counts CHECK (progress_total >= 0 AND progress_done >= 0 AND failed_count >= 0 AND cancelled_count >= 0),
    CONSTRAINT uq_ai_task_job_idempotency UNIQUE (actor_id, project_id, task_kind, idempotency_key)
);

CREATE TABLE IF NOT EXISTS ai_task_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES ai_task_jobs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    target_type VARCHAR(24) NOT NULL,
    target_id UUID NOT NULL,
    target_key VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    generation_id UUID NOT NULL DEFAULT gen_random_uuid(),
    message_id UUID REFERENCES ai_chat_message(id) ON DELETE SET NULL,
    baseline_version VARCHAR(80),
    before_hash CHAR(64),
    request_hash CHAR(64) NOT NULL,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_summary JSONB,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_attempt_at TIMESTAMPTZ,
    lease_owner VARCHAR(128),
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    error_code VARCHAR(64),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ai_task_item_type CHECK (target_type IN ('note_section','workpaper')),
    CONSTRAINT ck_ai_task_item_status CHECK (status IN ('queued','running','retry_wait','succeeded','failed','cancelled')),
    CONSTRAINT ck_ai_task_item_attempts CHECK (attempt_count >= 0 AND max_attempts > 0),
    CONSTRAINT ck_ai_task_item_lease CHECK ((lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR (lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)),
    CONSTRAINT uq_ai_task_item_target UNIQUE (job_id, target_type, target_id, target_key),
    CONSTRAINT uq_ai_task_item_ordinal UNIQUE (job_id, ordinal),
    CONSTRAINT uq_ai_task_item_generation UNIQUE (generation_id)
);

CREATE INDEX IF NOT EXISTS ix_ai_task_jobs_project_created ON ai_task_jobs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_task_items_claim ON ai_task_items(status, next_attempt_at, lease_expires_at);
CREATE INDEX IF NOT EXISTS ix_ai_task_items_job_status ON ai_task_items(job_id, status);
