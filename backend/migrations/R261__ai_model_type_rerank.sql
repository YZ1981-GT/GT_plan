-- R261: 回滚 V261（ai_model_type_enum 的 'rerank'）
-- PostgreSQL 不支持从 enum 类型移除已加入的值（无 DROP VALUE），与 R168 / R192 同口径保留标签。
-- 使用该值的行与索引已由 R262 停用 / 删除，故本回滚为有意的 no-op。
SELECT 1;
