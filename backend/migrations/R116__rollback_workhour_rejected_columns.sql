-- R116: 回滚 V116（工时退回/批准列）。
DO $$
BEGIN
    IF to_regclass('public.work_hours') IS NOT NULL
       AND EXISTS (SELECT 1 FROM work_hours WHERE rejected_reason IS NOT NULL OR approved_by IS NOT NULL OR approved_at IS NOT NULL) THEN
        RAISE EXCEPTION 'R116 拒绝回滚：work_hours 已保存退回或批准事实';
    END IF;
END $$;
ALTER TABLE work_hours DROP COLUMN IF EXISTS approved_at;
ALTER TABLE work_hours DROP COLUMN IF EXISTS approved_by;
ALTER TABLE work_hours DROP COLUMN IF EXISTS rejected_reason;
