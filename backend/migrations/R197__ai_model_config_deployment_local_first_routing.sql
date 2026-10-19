-- R197: 回滚到「每类一条启用」。
-- 同类型（OCR 同能力槽）同时启用了本机与服务器时只保留服务器那条：
-- V197 之前服务器行是用户显式激活的那一条，本机行是 V197 之后才能并存的。

UPDATE ai_model_config AS l
SET is_active = false,
    updated_at = NOW()
WHERE l.is_active = true
  AND l.is_deleted = false
  AND l.deployment = 'local'
  AND EXISTS (
      SELECT 1
      FROM ai_model_config AS s
      WHERE s.is_active = true
        AND s.is_deleted = false
        AND s.deployment = 'server'
        AND s.model_type = l.model_type
        AND COALESCE(s.ocr_capability, '') = COALESCE(l.ocr_capability, '')
  );

DROP INDEX IF EXISTS uq_ai_model_config_active_ocr_route;
DROP INDEX IF EXISTS uq_ai_model_config_active_embedding;
DROP INDEX IF EXISTS uq_ai_model_config_active_chat_route;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_config_active_non_ocr
    ON ai_model_config (model_type)
    WHERE is_active = true AND is_deleted = false
      AND model_type <> 'ocr'::ai_model_type_enum;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_config_active_ocr_capability
    ON ai_model_config (ocr_capability)
    WHERE is_active = true AND is_deleted = false
      AND model_type = 'ocr'::ai_model_type_enum;

ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_deployment;
ALTER TABLE ai_model_config DROP COLUMN IF EXISTS deployment;
