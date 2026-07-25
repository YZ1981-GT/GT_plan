-- R125: 回滚 V125（调整分录协作接力）
-- 安全回滚：先 drop 依赖表（event → collaboration）。默认保留数据以防丢失协作历史。

-- 如需彻底回滚（会丢失全部协作记录与历史），取消注释：
-- DROP TABLE IF EXISTS adjustment_collaboration_event;
-- DROP TABLE IF EXISTS adjustment_collaboration;

-- 默认仅 drop 索引（保表保数据）：
DROP INDEX IF EXISTS idx_adj_collab_event_collab_time;
DROP INDEX IF EXISTS idx_adj_collab_project_status;
DROP INDEX IF EXISTS idx_adj_collab_assignee_status;
DROP INDEX IF EXISTS idx_adj_collab_project_group;
