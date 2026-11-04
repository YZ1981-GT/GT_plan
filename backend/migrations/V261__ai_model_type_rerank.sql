-- V261: 模型类型新增 rerank（检索结果重排，spec enterprise-embedding-rerank-closure R2）
-- 只加枚举值：ADD VALUE 在事务内执行时新值要等提交后才能使用，
-- 用到 'rerank' 的启用唯一索引与预设种子放在 V262。
ALTER TYPE ai_model_type_enum ADD VALUE IF NOT EXISTS 'rerank';
