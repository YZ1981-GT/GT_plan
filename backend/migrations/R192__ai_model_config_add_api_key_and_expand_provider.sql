-- R192: 回滚 V192 的列与索引。
-- PostgreSQL enum label 无安全删除语义，deepseek/zhipu/qwen/azure_openai/custom 保留。

DROP INDEX IF EXISTS uq_ai_model_config_active_type;
DROP INDEX IF EXISTS ix_ai_model_config_name_type;
CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_model_config_name_type
    ON ai_model_config (model_name, model_type);

ALTER TABLE ai_model_config
    DROP COLUMN IF EXISTS api_key_updated_at,
    DROP COLUMN IF EXISTS api_key_ciphertext;
