-- V192: 外部 LLM 提供商运行时配置闭环
-- 密钥只存 Fernet 密文；PG enum 采用 additive 迁移（label 不做回滚）。

ALTER TABLE ai_model_config
    ADD COLUMN IF NOT EXISTS api_key_ciphertext TEXT,
    ADD COLUMN IF NOT EXISTS api_key_updated_at TIMESTAMPTZ;

COMMENT ON COLUMN ai_model_config.api_key_ciphertext
    IS 'v1: 前缀的 Fernet 密文；禁止存储或返回明文 API Key';
COMMENT ON COLUMN ai_model_config.api_key_updated_at
    IS 'API Key 最近替换或显式清除时间（UTC）';

-- 新 provider 均由统一 runtime adapter 消费；本迁移内不立即写入新 label。
ALTER TYPE ai_provider_enum ADD VALUE IF NOT EXISTS 'deepseek';
ALTER TYPE ai_provider_enum ADD VALUE IF NOT EXISTS 'zhipu';
ALTER TYPE ai_provider_enum ADD VALUE IF NOT EXISTS 'qwen';
ALTER TYPE ai_provider_enum ADD VALUE IF NOT EXISTS 'azure_openai';
ALTER TYPE ai_provider_enum ADD VALUE IF NOT EXISTS 'custom';

-- 软删除后允许重建同名模型；未删除行仍保持 name/type 唯一。
DROP INDEX IF EXISTS ix_ai_model_config_name_type;
CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_model_config_name_type
    ON ai_model_config (model_name, model_type)
    WHERE is_deleted = false;

-- 每种模型类型最多一个 active row；并发 activate 由此约束兜底。
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_config_active_type
    ON ai_model_config (model_type)
    WHERE is_active = true AND is_deleted = false;
