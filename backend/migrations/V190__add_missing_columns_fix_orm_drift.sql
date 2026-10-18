-- V190：补建 8 个 ORM 定义但 PG 缺失的列
--
-- 启动日志 schema drift critical=9 中除 share_change_event 表（V189）外的全部。
-- 所有 ADD COLUMN 幂等（IF NOT EXISTS）。

-- 1. consol_worksheet_data.version  (BigInteger, NOT NULL DEFAULT 0)
ALTER TABLE consol_worksheet_data
    ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0;

-- 2. draft_refresh_snapshot.source_scope  (JSONB, nullable)
ALTER TABLE draft_refresh_snapshot
    ADD COLUMN IF NOT EXISTS source_scope JSONB;

-- 3. draft_refresh_snapshot.source_formula_id  (UUID, nullable)
ALTER TABLE draft_refresh_snapshot
    ADD COLUMN IF NOT EXISTS source_formula_id UUID;

-- 4. export_job_attempts.trigger_source  (VARCHAR(30), nullable)
ALTER TABLE export_job_attempts
    ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(30);

-- 5. report_config.aje_formula  (TEXT, nullable)
ALTER TABLE report_config
    ADD COLUMN IF NOT EXISTS aje_formula TEXT;

-- 6. report_config.rje_formula  (TEXT, nullable)
ALTER TABLE report_config
    ADD COLUMN IF NOT EXISTS rje_formula TEXT;

-- 7. wp_formula.source_scope  (JSONB, nullable)
ALTER TABLE wp_formula
    ADD COLUMN IF NOT EXISTS source_scope JSONB;

-- 8. wp_formula.binding  (JSONB, nullable)
ALTER TABLE wp_formula
    ADD COLUMN IF NOT EXISTS binding JSONB;
