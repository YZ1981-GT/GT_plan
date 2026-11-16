-- R097: 回滚 V097（底稿快照）。
-- 快照是版本/恢复依据；有任何行时拒绝自动删除。
DO $$
BEGIN
    IF to_regclass('public.workpaper_snapshots') IS NOT NULL
       AND EXISTS (SELECT 1 FROM workpaper_snapshots LIMIT 1) THEN
        RAISE EXCEPTION 'R097 拒绝回滚：workpaper_snapshots 存在快照数据';
    END IF;
END $$;
DROP INDEX IF EXISTS idx_wp_snapshots_project;
DROP INDEX IF EXISTS idx_wp_snapshots_wp_created;
DROP TABLE IF EXISTS workpaper_snapshots;
