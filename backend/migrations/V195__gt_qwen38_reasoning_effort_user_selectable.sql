-- V195: 企业 qwen3.8 预设的思考强度改为「未指定」，由用户在模型配置页自行选择。
-- 只回退 V194 播种的原值 'low'（此前预设参数锁定，用户无法修改该值）。
UPDATE ai_model_config
SET reasoning_effort = NULL,
    updated_at = NOW()
WHERE preset_key = 'gt_qwen38'
  AND is_deleted = false
  AND reasoning_effort = 'low';
