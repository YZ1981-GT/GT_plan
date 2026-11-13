-- V271: 补建致同企业向量模型预设（dev1.0 合并 spec/disclosure-note-doc-upload-and-batch-fill 时发现的固定 id 撞号）
-- V208（dev1.0）把 71d00d01-a5b3-4ad7-9f2a-000000000004 给了 qwen3.7-max；V262（spec）又用同一个 id 建向量预设，
-- 其 WHERE NOT EXISTS 先按 id 判断 ⇒ 已有 qwen3.7-max 的库里向量预设被静默跳过。
-- 这里按 preset_key / model_name 判断缺行再补建，id 改用 …0006（与 ai_model_presets.GT_WEMM_EMBEDDING_4B 一致）。
-- 已由 V262 建好向量预设的库（id …0004）不受影响：预设按 preset_key / model_name 认行，不按 id。
INSERT INTO ai_model_config (
    id, preset_key, model_name, model_type, provider, endpoint_url,
    is_active, is_deleted, deployment, trust_zone, client_data_allowed, mask_policy,
    performance_notes, created_at, updated_at
)
SELECT
    '71d00d01-a5b3-4ad7-9f2a-000000000006'::uuid,
    'gt_wemm_embedding_4b', 'wemm-embedding-4b', 'embedding'::ai_model_type_enum,
    'custom'::ai_provider_enum, 'https://ai.gt-china.com.cn:10010/v1',
    false, false, 'server', 'firm_private', true, 'strict',
    '致同企业向量模型预设（输出 1024 维，与知识库索引一致）；只需录入 API Key', NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM ai_model_config
    WHERE id = '71d00d01-a5b3-4ad7-9f2a-000000000006'::uuid
       OR (is_deleted = false AND preset_key = 'gt_wemm_embedding_4b')
       OR (is_deleted = false AND model_name = 'wemm-embedding-4b'
           AND model_type = 'embedding'::ai_model_type_enum)
);
