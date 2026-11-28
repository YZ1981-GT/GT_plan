-- R210：回滚 V210（撤销 sampled_vouchers 的主体 / 凭证字 / 阶段列与按凭证键去重的两条唯一索引）
--
-- 🔴 回滚会收紧约束：V210 允许「同日同号不同凭证字（或不同主体）分别挂凭」与「同一批次登记
--    同号不同日的凭证」，恢复 V166 / V139 的索引后这些行会违约。先检测冲突，有冲突就抛错
--    让人裁决 —— 挂凭与抽凭登记是审计留痕，本回滚不静默删除。
-- 🔴 顺序：先把两条索引恢复成旧形态（新列仍在，不影响旧索引），再删约束与列；
--    反过来先删列会级联删掉含该列的表达式索引，旧索引若因冲突建不起来就留下无约束的裸表。
DO $$
DECLARE
    manual_conflicts bigint;
    batch_conflicts bigint;
BEGIN
    IF to_regclass('sampled_vouchers') IS NULL THEN
        RETURN;
    END IF;

    SELECT COALESCE(SUM(cnt - 1), 0) INTO manual_conflicts
    FROM (
        SELECT COUNT(*) AS cnt
        FROM sampled_vouchers
        WHERE is_deleted = false AND batch_id IS NULL
        GROUP BY project_id, year, voucher_no,
                 COALESCE(voucher_date, DATE '1900-01-01'),
                 COALESCE(working_paper_id, '00000000-0000-0000-0000-000000000000'::uuid)
        HAVING COUNT(*) > 1
    ) dup;

    SELECT COALESCE(SUM(cnt - 1), 0) INTO batch_conflicts
    FROM (
        SELECT COUNT(*) AS cnt
        FROM sampled_vouchers
        WHERE is_deleted = false AND batch_id IS NOT NULL
        GROUP BY project_id, year, voucher_no, working_paper_id, batch_id
        HAVING COUNT(*) > 1
    ) dup;

    IF manual_conflicts > 0 OR batch_conflicts > 0 THEN
        RAISE EXCEPTION
            'R210 拒绝回滚：恢复旧唯一索引后手工挂凭 % 行、批次登记 % 行会违约'
            '（同日同号不同凭证字 / 不同主体分别挂凭，或同一批次登记了同号不同日的凭证）。'
            '这些是审计留痕，本回滚不静默删除；请先人工裁决。',
            manual_conflicts, batch_conflicts;
    END IF;

    DROP INDEX IF EXISTS uq_sampled_voucher_manual_project_year_no;
    CREATE UNIQUE INDEX uq_sampled_voucher_manual_project_year_no
      ON sampled_vouchers (
          project_id,
          year,
          voucher_no,
          (COALESCE(voucher_date, DATE '1900-01-01')),
          (COALESCE(working_paper_id, '00000000-0000-0000-0000-000000000000'::uuid))
      )
      WHERE is_deleted = false AND batch_id IS NULL;

    DROP INDEX IF EXISTS uq_sampled_vouchers_batch;
    CREATE UNIQUE INDEX uq_sampled_vouchers_batch
      ON sampled_vouchers (project_id, year, voucher_no, working_paper_id, batch_id)
      WHERE is_deleted = false;

    ALTER TABLE sampled_vouchers DROP CONSTRAINT IF EXISTS ck_sampled_vouchers_phase;
    ALTER TABLE sampled_vouchers DROP COLUMN IF EXISTS phase;
    ALTER TABLE sampled_vouchers DROP COLUMN IF EXISTS voucher_type;
    ALTER TABLE sampled_vouchers DROP COLUMN IF EXISTS company_code;
END $$;
