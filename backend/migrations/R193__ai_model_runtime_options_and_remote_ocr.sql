-- R193: 回滚运行参数与 OCR capability 配置。
-- 若 ocr/layout_parsing 同时 active，旧的 per-type 唯一索引会拒绝回滚，避免静默丢状态。

DROP INDEX IF EXISTS uq_ai_model_config_active_ocr_capability;
DROP INDEX IF EXISTS uq_ai_model_config_active_non_ocr;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_config_active_type
    ON ai_model_config (model_type)
    WHERE is_active = true AND is_deleted = false;

ALTER TABLE ai_model_config
    DROP CONSTRAINT IF EXISTS ck_ai_model_ocr_runtime_fields,
    DROP CONSTRAINT IF EXISTS ck_ai_model_timeout,
    DROP CONSTRAINT IF EXISTS ck_ai_model_auth_scheme,
    DROP CONSTRAINT IF EXISTS ck_ai_model_ocr_protocol,
    DROP CONSTRAINT IF EXISTS ck_ai_model_ocr_capability,
    DROP CONSTRAINT IF EXISTS ck_ai_model_reasoning_effort;

ALTER TABLE ai_model_config
    DROP COLUMN IF EXISTS request_timeout_seconds,
    DROP COLUMN IF EXISTS auth_header_name,
    DROP COLUMN IF EXISTS auth_scheme,
    DROP COLUMN IF EXISTS ocr_protocol,
    DROP COLUMN IF EXISTS ocr_capability,
    DROP COLUMN IF EXISTS api_path,
    DROP COLUMN IF EXISTS reasoning_effort;
