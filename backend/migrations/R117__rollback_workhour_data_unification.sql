-- R117: 回滚 V117（work_hours -> work_hour_entries 数据统一）。
-- 迁移生成随机 ID，且无法从当前表可靠区分迁移行与既有行；拒绝反向 DELETE，避免误删工时。
DO $$ BEGIN
    RAISE EXCEPTION 'R117 拒绝自动回滚：工时数据已迁入 work_hour_entries，请按迁移前快照逐行恢复';
END $$;
