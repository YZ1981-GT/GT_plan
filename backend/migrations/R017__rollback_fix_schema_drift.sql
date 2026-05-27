-- R017__rollback_fix_schema_drift.sql
-- 回滚 V017：移除 import_jobs 三个补列；保留 job_status_enum 改名（无法安全回滚 ENUM 类型）。

BEGIN;

ALTER TABLE import_jobs DROP COLUMN IF EXISTS creator_chain;
ALTER TABLE import_jobs DROP COLUMN IF EXISTS force_submit;
ALTER TABLE import_jobs DROP COLUMN IF EXISTS version;

-- NOTE: job_status_enum 重命名不回滚（如需，可手动 ALTER TYPE rename 回 job_status）。

COMMIT;
