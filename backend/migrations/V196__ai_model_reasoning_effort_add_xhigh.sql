-- V196: 思考强度增加 xhigh。
-- 企业 qwen3.8 网关实测只接受 low / medium / xhigh（未指定时默认 xhigh），传 high 返回 400。
ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_reasoning_effort;
ALTER TABLE ai_model_config ADD CONSTRAINT ck_ai_model_reasoning_effort
    CHECK (reasoning_effort IS NULL OR reasoning_effort IN ('low', 'medium', 'high', 'xhigh'));
