-- V120: 为 ai_content_type_enum 添加 'review_finding' 值
-- batch_review_service 复核结果持久化需要该类型
-- 幂等: ADD VALUE IF NOT EXISTS (PG 9.3+)

ALTER TYPE ai_content_type_enum ADD VALUE IF NOT EXISTS 'review_finding';
