-- V193: 企业 OpenAI-compatible 运行参数 + 远程 PaddleX OCR 配置

ALTER TABLE ai_model_config
    ADD COLUMN IF NOT EXISTS reasoning_effort VARCHAR(16),
    ADD COLUMN IF NOT EXISTS api_path VARCHAR(128),
    ADD COLUMN IF NOT EXISTS ocr_capability VARCHAR(32),
    ADD COLUMN IF NOT EXISTS ocr_protocol VARCHAR(32),
    ADD COLUMN IF NOT EXISTS auth_scheme VARCHAR(32),
    ADD COLUMN IF NOT EXISTS auth_header_name VARCHAR(128),
    ADD COLUMN IF NOT EXISTS request_timeout_seconds INTEGER;

-- 既有本地 PaddleOCR 配置显式化，避免 NULL 被误判为远程降级。
UPDATE ai_model_config
SET ocr_capability = COALESCE(ocr_capability, 'ocr'),
    ocr_protocol = COALESCE(ocr_protocol, 'local'),
    auth_scheme = COALESCE(auth_scheme, 'none')
WHERE model_type = 'ocr'::ai_model_type_enum;

ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_reasoning_effort;
ALTER TABLE ai_model_config ADD CONSTRAINT ck_ai_model_reasoning_effort
    CHECK (reasoning_effort IS NULL OR reasoning_effort IN ('low', 'medium', 'high'));
ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_ocr_capability;
ALTER TABLE ai_model_config ADD CONSTRAINT ck_ai_model_ocr_capability
    CHECK (ocr_capability IS NULL OR ocr_capability IN ('ocr', 'layout_parsing'));
ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_ocr_protocol;
ALTER TABLE ai_model_config ADD CONSTRAINT ck_ai_model_ocr_protocol
    CHECK (ocr_protocol IS NULL OR ocr_protocol IN ('local', 'paddlex_json'));
ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_auth_scheme;
ALTER TABLE ai_model_config ADD CONSTRAINT ck_ai_model_auth_scheme
    CHECK (auth_scheme IS NULL OR auth_scheme IN ('none', 'bearer', 'x_api_key', 'api_key', 'custom_header'));
ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_timeout;
ALTER TABLE ai_model_config ADD CONSTRAINT ck_ai_model_timeout
    CHECK (request_timeout_seconds IS NULL OR request_timeout_seconds BETWEEN 1 AND 600);
ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_ocr_runtime_fields;
ALTER TABLE ai_model_config ADD CONSTRAINT ck_ai_model_ocr_runtime_fields CHECK (
    model_type <> 'ocr'::ai_model_type_enum
    OR (ocr_capability IS NOT NULL AND ocr_protocol IS NOT NULL)
);

-- chat/embedding 各最多一个 active；OCR 按 capability 各最多一个 active。
DROP INDEX IF EXISTS uq_ai_model_config_active_type;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_config_active_non_ocr
    ON ai_model_config (model_type)
    WHERE is_active = true AND is_deleted = false
      AND model_type <> 'ocr'::ai_model_type_enum;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_config_active_ocr_capability
    ON ai_model_config (ocr_capability)
    WHERE is_active = true AND is_deleted = false
      AND model_type = 'ocr'::ai_model_type_enum;
