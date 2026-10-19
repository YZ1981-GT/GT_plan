-- R196: 回滚 V196 —— xhigh 记录先改回「未指定」，再恢复 V193 的取值约束。
UPDATE ai_model_config
SET reasoning_effort = NULL,
    updated_at = NOW()
WHERE reasoning_effort = 'xhigh';

ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_reasoning_effort;
ALTER TABLE ai_model_config ADD CONSTRAINT ck_ai_model_reasoning_effort
    CHECK (reasoning_effort IS NULL OR reasoning_effort IN ('low', 'medium', 'high'));
