-- V208: 新增致同企业 Qwen 3.7 Max 对话模型预设（2026-10-27 用户要求接入）
-- 端点与 gt_qwen38 同一企业网关（https://ai.gt-china.com.cn:10010/v1，
-- OpenAI-compatible），经 ai_model_presets.BUILTIN_TRUSTED_ENDPOINTS 精确放行；
-- 仅需在 AI 模型配置页录入 API Key（Fernet 密文落库，需服务端 ENCRYPTION_KEY）。
-- 幂等写法同 V194：WHERE NOT EXISTS（model_name + model_type + is_deleted=false）。
-- reasoning_effort 留 NULL（未指定=不发该参数，服务端默认 xhigh；V195/V196 口径）。

INSERT INTO ai_model_config (
    id, preset_key, model_name, model_type, provider, endpoint_url,
    context_window, reasoning_effort, is_active, is_deleted,
    performance_notes, created_at, updated_at
)
SELECT
    '71d00d01-a5b3-4ad7-9f2a-000000000004'::uuid,
    'gt_qwen37_max', 'qwen3.7-max', 'chat'::ai_model_type_enum,
    'custom'::ai_provider_enum, 'https://ai.gt-china.com.cn:10010/v1',
    262144, NULL, false, false,
    '致同企业 OpenAI-compatible 预设；只需录入 API Key', NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM ai_model_config
    WHERE model_name = 'qwen3.7-max' AND model_type = 'chat'::ai_model_type_enum
      AND is_deleted = false
);
