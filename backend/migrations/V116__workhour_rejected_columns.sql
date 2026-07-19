-- V116: work_hours 表增加审批退回/批准相关列
-- 对齐 ORM staff_models.WorkHour 新增的 rejected_reason / approved_by / approved_at
-- 幂等：information_schema.columns 检测列存在性

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'work_hours' AND column_name = 'rejected_reason') THEN
    ALTER TABLE work_hours ADD COLUMN rejected_reason TEXT;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'work_hours' AND column_name = 'approved_by') THEN
    ALTER TABLE work_hours ADD COLUMN approved_by UUID REFERENCES users(id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'work_hours' AND column_name = 'approved_at') THEN
    ALTER TABLE work_hours ADD COLUMN approved_at TIMESTAMPTZ;
  END IF;
END $$;
