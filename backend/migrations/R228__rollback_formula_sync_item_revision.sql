-- R228: 回滚 V228（formula_sync_item.revision）
-- 回滚后新代码读写该列即报错（列不存在）：先回退代码，再执行本回滚。
ALTER TABLE formula_sync_item DROP COLUMN IF EXISTS revision;
