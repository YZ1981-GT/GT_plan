-- R195: 回滚 V195 —— 企业 qwen3.8 预设仍为「未指定」时恢复 V194 的 'low'。
UPDATE ai_model_config
SET reasoning_effort = 'low',
    updated_at = NOW()
WHERE preset_key = 'gt_qwen38'
  AND is_deleted = false
  AND reasoning_effort IS NULL;
