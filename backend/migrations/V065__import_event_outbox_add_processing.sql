-- V065: 为 import_event_outbox_status enum 增加 'processing' 值
-- 根因：event_cascade_health_service 查询使用了 'processing' 状态，但 enum 缺少该值导致导入中断
-- 注意：ALTER TYPE ADD VALUE 不支持事务包裹，但 IF NOT EXISTS 保证幂等

ALTER TYPE import_event_outbox_status ADD VALUE IF NOT EXISTS 'processing';
