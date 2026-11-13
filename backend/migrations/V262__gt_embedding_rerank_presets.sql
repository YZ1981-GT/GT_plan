-- V262: 致同企业向量 / 重排模型预设 + 重排启用唯一约束（spec enterprise-embedding-rerank-closure R1 / R2）
-- 只存公开配置，绝不预置 API Key（与 V194 同口径）。两者与 qwen3.8 同一网关：
-- 2026-11-04 实测 GET /v1/models 列出 wemm-embedding-4b、qwen3.8、qwen3-reranker-4b。
-- 依赖 V261 已提交的 'rerank' 枚举值。信任字段按 V237 预设行口径：事务所私有、允许客户数据、严格脱敏。

-- 重排与对话同一启用约束：本机、服务器各最多一条
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_config_active_rerank_route
    ON ai_model_config (model_type, deployment)
    WHERE is_active = true AND is_deleted = false
      AND model_type = 'rerank'::ai_model_type_enum;

INSERT INTO ai_model_config (
    id, preset_key, model_name, model_type, provider, endpoint_url,
    is_active, is_deleted, deployment, trust_zone, client_data_allowed, mask_policy,
    performance_notes, created_at, updated_at
)
SELECT
    '71d00d01-a5b3-4ad7-9f2a-000000000004'::uuid,
    'gt_wemm_embedding_4b', 'wemm-embedding-4b', 'embedding'::ai_model_type_enum,
    'custom'::ai_provider_enum, 'https://ai.gt-china.com.cn:10010/v1',
    false, false, 'server', 'firm_private', true, 'strict',
    '致同企业向量模型预设（输出 1024 维，与知识库索引一致）；只需录入 API Key', NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM ai_model_config
    WHERE id = '71d00d01-a5b3-4ad7-9f2a-000000000004'::uuid
       OR (is_deleted = false AND preset_key = 'gt_wemm_embedding_4b')
       OR (is_deleted = false AND model_name = 'wemm-embedding-4b'
           AND model_type = 'embedding'::ai_model_type_enum)
);

INSERT INTO ai_model_config (
    id, preset_key, model_name, model_type, provider, endpoint_url,
    is_active, is_deleted, deployment, trust_zone, client_data_allowed, mask_policy,
    performance_notes, created_at, updated_at
)
SELECT
    '71d00d01-a5b3-4ad7-9f2a-000000000005'::uuid,
    'gt_qwen3_reranker_4b', 'qwen3-reranker-4b', 'rerank'::ai_model_type_enum,
    'custom'::ai_provider_enum, 'https://ai.gt-china.com.cn:10010/v1',
    false, false, 'server', 'firm_private', true, 'strict',
    '致同企业重排模型预设（知识检索结果二次排序）；只需录入 API Key', NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM ai_model_config
    WHERE id = '71d00d01-a5b3-4ad7-9f2a-000000000005'::uuid
       OR (is_deleted = false AND preset_key = 'gt_qwen3_reranker_4b')
       OR (is_deleted = false AND model_name = 'qwen3-reranker-4b'
           AND model_type = 'rerank'::ai_model_type_enum)
);
