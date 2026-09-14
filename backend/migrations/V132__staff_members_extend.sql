-- V132: 人员档案字段扩展（执业资质/状态/头像）
-- 幂等: 用 information_schema 守护

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'staff_members' AND column_name = 'is_cpa') THEN
    ALTER TABLE staff_members ADD COLUMN is_cpa BOOLEAN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'staff_members' AND column_name = 'cpa_cert_no') THEN
    ALTER TABLE staff_members ADD COLUMN cpa_cert_no VARCHAR(50);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'staff_members' AND column_name = 'audit_years') THEN
    ALTER TABLE staff_members ADD COLUMN audit_years INTEGER;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'staff_members' AND column_name = 'qualifications') THEN
    ALTER TABLE staff_members ADD COLUMN qualifications JSONB;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'staff_members' AND column_name = 'industry_experience') THEN
    ALTER TABLE staff_members ADD COLUMN industry_experience JSONB;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'staff_members' AND column_name = 'status') THEN
    ALTER TABLE staff_members ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'staff_members' AND column_name = 'avatar_url') THEN
    ALTER TABLE staff_members ADD COLUMN avatar_url VARCHAR(500);
  END IF;
END $$;
