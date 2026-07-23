-- R123: 回滚 V123 抽样批次治理（幂等）
DROP INDEX IF EXISTS idx_extraction_log_batch;
DROP INDEX IF EXISTS uq_extraction_log_batch_undone;
DROP INDEX IF EXISTS uq_extraction_log_wp_idempotency;

ALTER TABLE workpaper_extraction_log DROP CONSTRAINT IF EXISTS fk_extraction_log_user;
ALTER TABLE workpaper_extraction_log DROP CONSTRAINT IF EXISTS chk_extraction_log_status;
ALTER TABLE workpaper_extraction_log DROP CONSTRAINT IF EXISTS chk_extraction_log_type;
ALTER TABLE workpaper_extraction_log DROP CONSTRAINT IF EXISTS chk_extraction_log_fill_mode;

ALTER TABLE workpaper_extraction_log DROP COLUMN IF EXISTS status;
ALTER TABLE workpaper_extraction_log DROP COLUMN IF EXISTS row_version;
ALTER TABLE workpaper_extraction_log DROP COLUMN IF EXISTS idempotency_key;
ALTER TABLE workpaper_extraction_log DROP COLUMN IF EXISTS batch_id;
