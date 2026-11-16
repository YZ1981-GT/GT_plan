-- R121: 回滚 V121（关联方明细 JSONB）。
DO $$
BEGIN
    IF to_regclass('public.related_party_registry') IS NOT NULL
       AND EXISTS (SELECT 1 FROM related_party_registry WHERE detail IS NOT NULL) THEN
        RAISE EXCEPTION 'R121 拒绝回滚：related_party_registry.detail 存在明细数据';
    END IF;
END $$;
ALTER TABLE related_party_registry DROP COLUMN IF EXISTS detail;
