-- V194: 致同企业 AI 模型预设（只存公开配置，绝不预置 API Key）

ALTER TABLE ai_model_config
    ADD COLUMN IF NOT EXISTS preset_key VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_config_preset_key
    ON ai_model_config (preset_key)
    WHERE preset_key IS NOT NULL AND is_deleted = false;

INSERT INTO ai_model_config (
    id, preset_key, model_name, model_type, provider, endpoint_url,
    context_window, reasoning_effort, is_active, is_deleted,
    performance_notes, created_at, updated_at
)
SELECT
    '71d00d01-a5b3-4ad7-9f2a-000000000001'::uuid,
    'gt_qwen38', 'qwen3.8', 'chat'::ai_model_type_enum,
    'custom'::ai_provider_enum, 'https://ai.gt-china.com.cn:10010/v1',
    262144, 'low', false, false,
    '致同企业 OpenAI-compatible 预设；只需录入 API Key', NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM ai_model_config
    WHERE model_name = 'qwen3.8' AND model_type = 'chat'::ai_model_type_enum
      AND is_deleted = false
);

INSERT INTO ai_model_config (
    id, preset_key, model_name, model_type, provider, endpoint_url,
    ocr_capability, ocr_protocol, api_path, auth_scheme,
    request_timeout_seconds, is_active, is_deleted,
    performance_notes, created_at, updated_at
)
SELECT
    '71d00d01-a5b3-4ad7-9f2a-000000000002'::uuid,
    'gt_paddleocrvl_16', 'paddleocrvl-1.6', 'ocr'::ai_model_type_enum,
    'paddleocr'::ai_provider_enum, 'https://ai.gt-china.com.cn:10080',
    'layout_parsing', 'paddlex_json', '/layout-parsing', 'bearer',
    120, false, false,
    '致同企业版面解析预设；只需录入 API Key', NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM ai_model_config
    WHERE model_name = 'paddleocrvl-1.6' AND model_type = 'ocr'::ai_model_type_enum
      AND is_deleted = false
);

INSERT INTO ai_model_config (
    id, preset_key, model_name, model_type, provider, endpoint_url,
    ocr_capability, ocr_protocol, api_path, auth_scheme,
    request_timeout_seconds, is_active, is_deleted,
    performance_notes, created_at, updated_at
)
SELECT
    '71d00d01-a5b3-4ad7-9f2a-000000000003'::uuid,
    'gt_paddleocrv6', 'paddleocrv6', 'ocr'::ai_model_type_enum,
    'paddleocr'::ai_provider_enum, 'https://ai.gt-china.com.cn:10080',
    'ocr', 'paddlex_json', '/ocr', 'bearer',
    60, false, false,
    '致同企业文字识别预设；只需录入 API Key', NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM ai_model_config
    WHERE model_name = 'paddleocrv6' AND model_type = 'ocr'::ai_model_type_enum
      AND is_deleted = false
);
