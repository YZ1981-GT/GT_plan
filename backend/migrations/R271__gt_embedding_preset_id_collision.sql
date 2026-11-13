-- R271: 回滚 V271 —— 只删 V271 补建、尚未录入 Key 且未启用的向量预设行
DELETE FROM ai_model_config
WHERE id = '71d00d01-a5b3-4ad7-9f2a-000000000006'::uuid
  AND preset_key = 'gt_wemm_embedding_4b'
  AND api_key_ciphertext IS NULL
  AND is_active = false;
