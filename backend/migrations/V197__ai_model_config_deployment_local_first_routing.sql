-- V197: 本机优先路由 —— 模型配置记录部署位置，启用约束改为按部署位置。
--
-- deployment：local = 进程内 OCR 引擎或环回端点（localhost / 127.0.0.0/8 / ::1）；其余 server。
-- 回填按端点字面判定、不做 DNS 解析；之后由应用层 classify_deployment() 在创建 / 更新时写入。
-- 启用语义：chat 本机、服务器各最多一条；embedding 仍只一条（向量不跨模型兜底）；
-- OCR 按能力槽本机、服务器各最多一条。

ALTER TABLE ai_model_config
    ADD COLUMN IF NOT EXISTS deployment VARCHAR(16);

UPDATE ai_model_config
SET deployment = CASE
    WHEN ocr_protocol = 'local' THEN 'local'
    WHEN endpoint_url IS NULL
         AND model_type <> 'ocr'::ai_model_type_enum
         AND provider IN ('openai_compatible'::ai_provider_enum, 'ollama'::ai_provider_enum)
        THEN 'local'
    WHEN endpoint_url ~* '^https?://(localhost|127\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|\[::1\])(:[0-9]+)?(/|$)'
        THEN 'local'
    ELSE 'server'
END
WHERE deployment IS NULL;

ALTER TABLE ai_model_config ALTER COLUMN deployment SET DEFAULT 'server';
ALTER TABLE ai_model_config ALTER COLUMN deployment SET NOT NULL;

ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_deployment;
ALTER TABLE ai_model_config ADD CONSTRAINT ck_ai_model_deployment
    CHECK (deployment IN ('local', 'server'));

DROP INDEX IF EXISTS uq_ai_model_config_active_non_ocr;
DROP INDEX IF EXISTS uq_ai_model_config_active_ocr_capability;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_config_active_chat_route
    ON ai_model_config (model_type, deployment)
    WHERE is_active = true AND is_deleted = false
      AND model_type = 'chat'::ai_model_type_enum;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_config_active_embedding
    ON ai_model_config (model_type)
    WHERE is_active = true AND is_deleted = false
      AND model_type = 'embedding'::ai_model_type_enum;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_config_active_ocr_route
    ON ai_model_config (ocr_capability, deployment)
    WHERE is_active = true AND is_deleted = false
      AND model_type = 'ocr'::ai_model_type_enum;
