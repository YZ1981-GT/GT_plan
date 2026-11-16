-- R100: 回滚 V100（公式管理库扩展）。
DO $$
BEGIN
    IF (to_regclass('public.draft_marker') IS NOT NULL AND EXISTS (SELECT 1 FROM draft_marker LIMIT 1))
       OR (to_regclass('public.draft_refresh_audit') IS NOT NULL AND EXISTS (SELECT 1 FROM draft_refresh_audit LIMIT 1))
       OR (to_regclass('public.draft_refresh_snapshot') IS NOT NULL AND EXISTS (SELECT 1 FROM draft_refresh_snapshot LIMIT 1)) THEN
        RAISE EXCEPTION 'R100 拒绝回滚：公式刷新/草稿审计数据存在';
    END IF;
END $$;
DROP TABLE IF EXISTS draft_refresh_snapshot;
DROP TABLE IF EXISTS draft_refresh_audit;
DROP TABLE IF EXISTS draft_marker;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS reference_formula_id;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS formula_source;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS hint_text;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS issue_description;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS refs;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS last_computed_at;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS formula_type;
