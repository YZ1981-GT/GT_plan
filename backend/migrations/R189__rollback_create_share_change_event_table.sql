-- R189: 回滚 V189（share_change_event）。
DO $$
BEGIN
    IF to_regclass('public.share_change_event') IS NOT NULL
       AND EXISTS (SELECT 1 FROM share_change_event LIMIT 1) THEN
        RAISE EXCEPTION 'R189 拒绝回滚：share_change_event 存在股权变动事件/审批数据';
    END IF;
END $$;
DROP TABLE IF EXISTS share_change_event;
