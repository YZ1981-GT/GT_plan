-- V185: 编辑锁增加客户端实例标识
-- spec: multi-window-ledger-workbench Phase 3 Task 13
--
-- 支持同一用户在不同浏览器标签页的锁隔离：
-- 同 user_id + 不同 client_instance → 视为锁冲突（第二个窗口只读）
-- 同 user_id + 同 client_instance → 视为续期（当前行为不变）

ALTER TABLE editing_locks ADD COLUMN IF NOT EXISTS client_instance VARCHAR(64);

-- 为活跃锁查询添加索引（按 resource 查活跃锁 + client_instance 过滤）
CREATE INDEX IF NOT EXISTS idx_editing_locks_client_instance
    ON editing_locks (resource_type, resource_id, client_instance)
    WHERE released_at IS NULL;
