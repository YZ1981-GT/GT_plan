-- R262: 回滚 V262（与 R194 同口径）
-- 只删尚未录入 Key、未启用的原始预设；已配置的保留，但脱离预设标识。
DELETE FROM ai_model_config
WHERE preset_key IN ('gt_wemm_embedding_4b', 'gt_qwen3_reranker_4b')
  AND api_key_ciphertext IS NULL
  AND is_active = false;

UPDATE ai_model_config
SET preset_key = NULL,
    updated_at = NOW()
WHERE preset_key IN ('gt_wemm_embedding_4b', 'gt_qwen3_reranker_4b');

-- 回滚后的应用不认识 rerank 类型（ORM 读到会抛 LookupError）：剩余重排行软删并清 Key
UPDATE ai_model_config
SET is_active = false,
    is_deleted = true,
    deleted_at = NOW(),
    api_key_ciphertext = NULL,
    updated_at = NOW()
WHERE model_type = 'rerank'::ai_model_type_enum
  AND is_deleted = false;

DROP INDEX IF EXISTS uq_ai_model_config_active_rerank_route;
