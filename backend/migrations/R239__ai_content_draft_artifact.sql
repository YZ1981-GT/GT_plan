-- R239: 回退 DraftArtifact 扩展（保留既有 ai_content_log）

DROP INDEX IF EXISTS ix_ai_content_log_pending_artifact;
DROP INDEX IF EXISTS ix_ai_content_log_source_message;
DROP INDEX IF EXISTS uq_ai_content_log_source_target;
DROP INDEX IF EXISTS uq_ai_content_log_generation;

ALTER TABLE ai_content_log DROP CONSTRAINT IF EXISTS ck_ai_content_log_writeback_status;
ALTER TABLE ai_content_log DROP CONSTRAINT IF EXISTS fk_ai_content_log_undone_by;
ALTER TABLE ai_content_log DROP CONSTRAINT IF EXISTS fk_ai_content_log_source_message;

ALTER TABLE ai_content_log DROP COLUMN IF EXISTS undone_at;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS undone_by;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS writeback_receipt;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS applied_hash;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS applied_version;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS writeback_status;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS artifact_version;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS preview_diff;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS proposed_hash;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS before_content;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS before_hash;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS baseline_version;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS target_locator;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS context_manifest;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS prompt_version;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS source_message_id;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS task_code;
ALTER TABLE ai_content_log DROP COLUMN IF EXISTS generation_id;
