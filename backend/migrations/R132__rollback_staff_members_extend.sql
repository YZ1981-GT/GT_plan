-- R132: 回滚 V132（staff_members 扩展列）。
DO $$
BEGIN
    IF to_regclass('public.staff_members') IS NOT NULL
       AND EXISTS (SELECT 1 FROM staff_members WHERE is_cpa OR cpa_cert_no IS NOT NULL OR audit_years IS NOT NULL OR qualifications IS NOT NULL OR industry_experience IS NOT NULL OR status <> 'active' OR avatar_url IS NOT NULL) THEN
        RAISE EXCEPTION 'R132 拒绝回滚：staff_members 已保存资质/状态/经验数据';
    END IF;
END $$;
ALTER TABLE staff_members DROP COLUMN IF EXISTS avatar_url;
ALTER TABLE staff_members DROP COLUMN IF EXISTS industry_experience;
ALTER TABLE staff_members DROP COLUMN IF EXISTS qualifications;
ALTER TABLE staff_members DROP COLUMN IF EXISTS audit_years;
ALTER TABLE staff_members DROP COLUMN IF EXISTS cpa_cert_no;
ALTER TABLE staff_members DROP COLUMN IF EXISTS is_cpa;
ALTER TABLE staff_members DROP COLUMN IF EXISTS status;
