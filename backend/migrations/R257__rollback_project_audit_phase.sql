-- R212：回滚 V212（删 interim_survival_checks；删 projects 的审计阶段与预审截止日两列及约束）
--
-- 🔴 预审截止日与核对汇总是审计留痕：有任何项目处于预审阶段、填过预审截止日，或核对表有行时
--    拒绝回滚，让人先裁决（本回滚不静默丢数据）。
DO $$
DECLARE
    phased bigint := 0;
    checks bigint := 0;
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'projects'
                 AND column_name = 'current_audit_phase') THEN
        EXECUTE 'SELECT count(*) FROM projects WHERE current_audit_phase <> ''final'' OR interim_cutoff_date IS NOT NULL'
            INTO phased;
    END IF;
    IF to_regclass('interim_survival_checks') IS NOT NULL THEN
        EXECUTE 'SELECT count(*) FROM interim_survival_checks' INTO checks;
    END IF;
    IF phased > 0 OR checks > 0 THEN
        RAISE EXCEPTION
            'R212 拒绝回滚：% 个项目设置了预审阶段或预审截止日、核对汇总表 % 行；请先人工裁决。',
            phased, checks;
    END IF;

    DROP TABLE IF EXISTS interim_survival_checks;
    ALTER TABLE projects DROP CONSTRAINT IF EXISTS ck_projects_current_audit_phase;
    ALTER TABLE projects DROP COLUMN IF EXISTS interim_cutoff_date;
    ALTER TABLE projects DROP COLUMN IF EXISTS current_audit_phase;
END $$;
