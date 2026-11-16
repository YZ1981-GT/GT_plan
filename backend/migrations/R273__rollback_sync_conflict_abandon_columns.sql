-- R273: 回滚 V273 的三列（abandoned_at / abandon_reason / abandoned_by）
--
-- protect-non-empty: working_paper_sync_conflict.abandoned_at
--
-- 🔴 只要有一行被作废过就拒绝回滚：作废是**审计事实**（谁在什么时候因为什么把一批
-- 冲突判为无意义），删掉这三列等于抹掉那条轨迹。要回滚必须先把作废事实导出/归档，
-- 再显式清空。用 `RAISE EXCEPTION` 而不是静默 DROP。
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM working_paper_sync_conflict WHERE abandoned_at IS NOT NULL LIMIT 1
    ) THEN
        RAISE EXCEPTION
            'working_paper_sync_conflict has abandoned rows; archive the abandon trail before rollback'
            USING ERRCODE = 'check_violation';
    END IF;
END
$$;

ALTER TABLE working_paper_sync_conflict
    DROP CONSTRAINT IF EXISTS ck_wpsc_abandon_triplet;
ALTER TABLE working_paper_sync_conflict
    DROP COLUMN IF EXISTS abandoned_by;
ALTER TABLE working_paper_sync_conflict
    DROP COLUMN IF EXISTS abandon_reason;
ALTER TABLE working_paper_sync_conflict
    DROP COLUMN IF EXISTS abandoned_at;
