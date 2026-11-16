-- R094: 回滚 V094（A13 未更正错报聚合列）。
DO $$
BEGIN
    IF to_regclass('public.unadjusted_misstatements') IS NOT NULL
       AND EXISTS (SELECT 1 FROM unadjusted_misstatements WHERE prior_year_status IS NOT NULL OR source_wp_code IS NOT NULL) THEN
        RAISE EXCEPTION 'R094 拒绝回滚：unadjusted_misstatements 已保存新增来源/上年状态数据';
    END IF;
END $$;
ALTER TABLE unadjusted_misstatements DROP COLUMN IF EXISTS source_wp_code;
ALTER TABLE unadjusted_misstatements DROP COLUMN IF EXISTS prior_year_status;
