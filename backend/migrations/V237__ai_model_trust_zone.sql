-- V237: 模型信任域、客户数据许可与最低脱敏策略
-- deployment 只描述位置；trust_zone 描述事务所对该端点的数据政策。

ALTER TABLE ai_model_config
    ADD COLUMN IF NOT EXISTS trust_zone VARCHAR(32),
    ADD COLUMN IF NOT EXISTS client_data_allowed BOOLEAN,
    ADD COLUMN IF NOT EXISTS mask_policy VARCHAR(16);

UPDATE ai_model_config
SET trust_zone = CASE
        WHEN deployment = 'local' THEN 'local_device'
        WHEN preset_key IS NOT NULL THEN 'firm_private'
        ELSE 'restricted'
    END,
    client_data_allowed = CASE
        WHEN deployment = 'local' OR preset_key IS NOT NULL THEN TRUE
        ELSE FALSE
    END,
    mask_policy = CASE
        WHEN deployment = 'local' THEN 'role_based'
        ELSE 'strict'
    END
WHERE trust_zone IS NULL OR client_data_allowed IS NULL OR mask_policy IS NULL;

ALTER TABLE ai_model_config
    ALTER COLUMN trust_zone SET DEFAULT 'restricted',
    ALTER COLUMN trust_zone SET NOT NULL,
    ALTER COLUMN client_data_allowed SET DEFAULT FALSE,
    ALTER COLUMN client_data_allowed SET NOT NULL,
    ALTER COLUMN mask_policy SET DEFAULT 'strict',
    ALTER COLUMN mask_policy SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ai_model_trust_zone') THEN
        ALTER TABLE ai_model_config ADD CONSTRAINT ck_ai_model_trust_zone
            CHECK (trust_zone IN ('local_device', 'firm_private', 'approved_provider', 'restricted'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ai_model_mask_policy') THEN
        ALTER TABLE ai_model_config ADD CONSTRAINT ck_ai_model_mask_policy
            CHECK (mask_policy IN ('none', 'role_based', 'strict'));
    END IF;
END $$;
