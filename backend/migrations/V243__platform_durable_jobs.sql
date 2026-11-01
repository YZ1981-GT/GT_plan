-- V243: 平台通用耐久任务、租约与 attempt 围栏

CREATE TABLE IF NOT EXISTS platform_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation VARCHAR(48) NOT NULL,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    actor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    payload_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    stage VARCHAR(64),
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    progress_message TEXT,
    reserved_bytes BIGINT NOT NULL DEFAULT 0,
    result_ref JSONB,
    error_code VARCHAR(80),
    error_message TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_attempt_at TIMESTAMPTZ,
    lease_owner VARCHAR(160),
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    cancel_requested_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 1,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_platform_jobs_status CHECK (
        status IN ('queued','running','retry_wait','succeeded','failed','cancelled')
    ),
    CONSTRAINT ck_platform_jobs_progress CHECK (
        progress_current >= 0 AND progress_total >= 0 AND reserved_bytes >= 0
    ),
    CONSTRAINT ck_platform_jobs_attempts CHECK (
        attempt_count >= 0 AND max_attempts > 0
    ),
    CONSTRAINT ck_platform_jobs_lease CHECK (
        (lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL)
        OR
        (lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
    ),
    CONSTRAINT uq_platform_jobs_idempotency UNIQUE (
        actor_id, project_id, operation, idempotency_key
    )
);

CREATE TABLE IF NOT EXISTS platform_job_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES platform_jobs(id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL,
    lease_token UUID NOT NULL,
    worker_id VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    error_code VARCHAR(80),
    error_message TEXT,
    CONSTRAINT ck_platform_job_attempt_status CHECK (
        status IN ('running','succeeded','failed','cancelled','lost_lease')
    ),
    CONSTRAINT uq_platform_job_attempt_no UNIQUE (job_id, attempt_no),
    CONSTRAINT uq_platform_job_attempt_token UNIQUE (lease_token)
);

CREATE INDEX IF NOT EXISTS ix_platform_jobs_claim
    ON platform_jobs (status, next_attempt_at, lease_expires_at, queued_at);
CREATE INDEX IF NOT EXISTS ix_platform_jobs_project_created
    ON platform_jobs (project_id, queued_at DESC);
CREATE INDEX IF NOT EXISTS ix_platform_job_attempts_job
    ON platform_job_attempts (job_id, attempt_no DESC);
