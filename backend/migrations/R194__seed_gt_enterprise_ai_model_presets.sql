-- R194: 只删除尚未录入 Key、未激活的原始预设；用户已配置的模型保留。
DELETE FROM ai_model_config
WHERE preset_key IN ('gt_qwen38', 'gt_paddleocrvl_16', 'gt_paddleocrv6')
  AND api_key_ciphertext IS NULL
  AND is_active = false;

-- 已录入 Key/已激活的记录脱离 preset 标识但不删除。
UPDATE ai_model_config
SET preset_key = NULL
WHERE preset_key IN ('gt_qwen38', 'gt_paddleocrvl_16', 'gt_paddleocrv6');

DROP INDEX IF EXISTS uq_ai_model_config_preset_key;
ALTER TABLE ai_model_config DROP COLUMN IF EXISTS preset_key;
