-- R102: 回滚 V102（高级查询回写审计）。
DO $$
BEGIN
    IF to_regclass('public.advanced_query_writeback') IS NOT NULL
       AND EXISTS (SELECT 1 FROM advanced_query_writeback LIMIT 1) THEN
        RAISE EXCEPTION 'R102 拒绝回滚：advanced_query_writeback 存在回写审计数据';
    END IF;
END $$;
DROP INDEX IF EXISTS idx_aqw_project;
DROP INDEX IF EXISTS idx_aqw_addr_id;
DROP TABLE IF EXISTS advanced_query_writeback;
