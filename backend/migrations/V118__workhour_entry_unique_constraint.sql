-- V118: work_hour_entries 加唯一约束防重复
-- 同一用户+项目+日期+循环 只能有一条记录
-- 幂等：pg_indexes 检测后创建

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE indexname = 'uq_work_hour_entries_user_project_date_cycle'
  ) THEN
    CREATE UNIQUE INDEX uq_work_hour_entries_user_project_date_cycle
      ON work_hour_entries (user_id, project_id, date, cycle);
  END IF;
END $$;

COMMENT ON INDEX uq_work_hour_entries_user_project_date_cycle IS
  '防止同用户+项目+日期+循环重复填报(V118)';
