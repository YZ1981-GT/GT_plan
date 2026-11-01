-- R237: 回滚模型信任域配置

ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_mask_policy;
ALTER TABLE ai_model_config DROP CONSTRAINT IF EXISTS ck_ai_model_trust_zone;
ALTER TABLE ai_model_config
    DROP COLUMN IF EXISTS mask_policy,
    DROP COLUMN IF EXISTS client_data_allowed,
    DROP COLUMN IF EXISTS trust_zone;
