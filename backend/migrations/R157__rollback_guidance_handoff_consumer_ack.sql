-- R157: 回滚 V157（guidance handoff/consumer ack）。
DO $$
BEGIN
    IF (to_regclass('public.guidance_consumer_ack') IS NOT NULL AND EXISTS (SELECT 1 FROM guidance_consumer_ack LIMIT 1))
       OR (to_regclass('public.guidance_handoff_visibility') IS NOT NULL AND EXISTS (SELECT 1 FROM guidance_handoff_visibility LIMIT 1)) THEN
        RAISE EXCEPTION 'R157 拒绝回滚：guidance ACK/visibility saga 数据存在';
    END IF;
END $$;
DROP TABLE IF EXISTS guidance_consumer_ack;
DROP TABLE IF EXISTS guidance_handoff_visibility;
