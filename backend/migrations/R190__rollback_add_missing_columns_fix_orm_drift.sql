-- R190: 回滚 V190（ORM drift 补列）。
DO $$
BEGIN
    IF (to_regclass('public.consol_worksheet_data') IS NOT NULL AND EXISTS (SELECT 1 FROM consol_worksheet_data WHERE version <> 0))
       OR (to_regclass('public.draft_refresh_snapshot') IS NOT NULL AND EXISTS (SELECT 1 FROM draft_refresh_snapshot WHERE source_scope IS NOT NULL OR source_formula_id IS NOT NULL))
       OR (to_regclass('public.export_job_attempts') IS NOT NULL AND EXISTS (SELECT 1 FROM export_job_attempts WHERE trigger_source IS NOT NULL))
       OR (to_regclass('public.report_config') IS NOT NULL AND EXISTS (SELECT 1 FROM report_config WHERE aje_formula IS NOT NULL OR rje_formula IS NOT NULL))
       OR (to_regclass('public.wp_formula') IS NOT NULL AND EXISTS (SELECT 1 FROM wp_formula WHERE source_scope IS NOT NULL OR binding IS NOT NULL)) THEN
        RAISE EXCEPTION 'R190 拒绝回滚：V190 补列已有业务数据';
    END IF;
END $$;
ALTER TABLE consol_worksheet_data DROP COLUMN IF EXISTS version;
ALTER TABLE draft_refresh_snapshot DROP COLUMN IF EXISTS source_formula_id;
ALTER TABLE draft_refresh_snapshot DROP COLUMN IF EXISTS source_scope;
ALTER TABLE export_job_attempts DROP COLUMN IF EXISTS trigger_source;
ALTER TABLE report_config DROP COLUMN IF EXISTS rje_formula;
ALTER TABLE report_config DROP COLUMN IF EXISTS aje_formula;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS binding;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS source_scope;
