-- R216：回滚 V216 底稿两阶段生成 operation/item
--
-- 先删引用父 operation 的 item，再删 operation。所有语句均可重复执行。

DROP INDEX IF EXISTS ix_wp_generation_items_operation_status;
DROP INDEX IF EXISTS uq_wp_generation_items_operation_ordinal;
DROP INDEX IF EXISTS uq_wp_generation_items_operation_code;
DROP TABLE IF EXISTS workpaper_generation_items;

DROP INDEX IF EXISTS ix_wp_generation_operations_lease;
DROP INDEX IF EXISTS ix_wp_generation_operations_project_status;
DROP TABLE IF EXISTS workpaper_generation_operations;
