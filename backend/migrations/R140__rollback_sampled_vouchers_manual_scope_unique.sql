-- R140: 回滚 V140（手工挂凭按项目/年度/凭证号唯一）。
-- 恢复旧全局唯一索引前先检查同项目/年度/凭证号冲突；冲突时拒绝，不静默删挂凭。
DO $$
BEGIN
    IF EXISTS (
        SELECT project_id, year, voucher_no
          FROM sampled_vouchers
         WHERE is_deleted = false AND batch_id IS NULL
         GROUP BY project_id, year, voucher_no
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'R140 拒绝回滚：手工挂凭记录会违反旧唯一索引';
    END IF;
END $$;
DROP INDEX IF EXISTS uq_sampled_vouchers_manual_project_year_no;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sampled_voucher_project_year_no
    ON sampled_vouchers(project_id, year, voucher_no)
    WHERE is_deleted = false;
