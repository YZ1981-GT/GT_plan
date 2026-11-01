-- V239: 在既有 ai_content_log 确认流上补齐 DraftArtifact 的版本、diff、CAS 与撤销字段

ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS generation_id UUID;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS task_code VARCHAR(80);
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS source_message_id UUID;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(32);
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS context_manifest JSONB;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS target_locator JSONB;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS baseline_version VARCHAR(80);
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS before_hash CHAR(64);
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS before_content TEXT;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS proposed_hash CHAR(64);
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS preview_diff JSONB;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS artifact_version BIGINT NOT NULL DEFAULT 0;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS writeback_status VARCHAR(20) NOT NULL DEFAULT 'pending';
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS applied_version VARCHAR(80);
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS applied_hash CHAR(64);
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS writeback_receipt JSONB;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS undone_by UUID;
ALTER TABLE ai_content_log ADD COLUMN IF NOT EXISTS undone_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_ai_content_log_source_message'
    ) THEN
        ALTER TABLE ai_content_log
            ADD CONSTRAINT fk_ai_content_log_source_message
            FOREIGN KEY (source_message_id) REFERENCES ai_chat_message(id) ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_ai_content_log_undone_by'
    ) THEN
        ALTER TABLE ai_content_log
            ADD CONSTRAINT fk_ai_content_log_undone_by
            FOREIGN KEY (undone_by) REFERENCES users(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_ai_content_log_writeback_status'
    ) THEN
        ALTER TABLE ai_content_log
            ADD CONSTRAINT ck_ai_content_log_writeback_status
            CHECK (writeback_status IN ('pending','applied','rejected','stale','manual_copy','undone'));
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_content_log_generation
    ON ai_content_log(generation_id) WHERE generation_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_content_log_source_target
    ON ai_content_log(source_message_id, target_cell)
    WHERE source_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_ai_content_log_source_message
    ON ai_content_log(source_message_id) WHERE source_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_ai_content_log_pending_artifact
    ON ai_content_log(project_id, writeback_status, generated_at DESC);
