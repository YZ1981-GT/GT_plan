-- R166：回滚 V166（撤销 voucher_date 列与手工去重索引的粒度细化）
--
-- 🔴 回滚顺序不可颠倒：必须先把索引恢复成 V140 的三列形态，再删列。
--    反之若先删 voucher_date，含该列的表达式索引会被 PG 级联删掉，
--    随后 CREATE 旧索引若因存量冲突失败，就会留下「既无新索引也无旧索引」的裸表。
--
-- 🔴 回滚会**收紧**约束：V166 允许「同一凭证挂多张底稿」与「同号不同日分别挂」，
--    恢复 V140 的三列唯一索引后这些行会违约。故先检测冲突，有冲突就抛错让人裁决 ——
--    静默删除挂凭记录比回滚失败危险得多（那是审计留痕）。

DO $$
DECLARE
    offending bigint;
BEGIN
    IF to_regclass('sampled_vouchers') IS NULL THEN
        RETURN;
    END IF;

    -- 恢复三列唯一索引后会撞车的行数（同 project+year+voucher_no 存在多行手工记录）
    SELECT COALESCE(SUM(cnt - 1), 0) INTO offending
    FROM (
        SELECT COUNT(*) AS cnt
        FROM sampled_vouchers
        WHERE is_deleted = false AND batch_id IS NULL
        GROUP BY project_id, year, voucher_no
        HAVING COUNT(*) > 1
    ) dup;

    IF offending > 0 THEN
        RAISE EXCEPTION
            'R166 拒绝回滚：有 % 行手工挂凭记录在恢复 V140 三列唯一索引后会违约'
            '（同一凭证挂了多张底稿，或同号不同日分别挂）。'
            '挂凭记录是审计留痕，本回滚不静默删除；请先人工裁决这些行的去向。',
            offending;
    END IF;

    -- 1. 先把索引恢复成 V140 形态（此时 voucher_date 列仍在）
    DROP INDEX IF EXISTS uq_sampled_voucher_manual_project_year_no;

    CREATE UNIQUE INDEX uq_sampled_voucher_manual_project_year_no
      ON sampled_vouchers (project_id, year, voucher_no)
      WHERE is_deleted = false AND batch_id IS NULL;

    COMMENT ON INDEX uq_sampled_voucher_manual_project_year_no IS
      '手工标记（batch_id IS NULL，来自 ledger_penetration 穿透页）的凭证去重；'
      '抽凭引擎登记走 uq_sampled_vouchers_batch 按批次唯一';

    -- 2. V166 新增的按底稿查询索引
    DROP INDEX IF EXISTS ix_sampled_vouchers_wp_scope;

    -- 3. 最后删列（此时已无索引依赖它）
    ALTER TABLE sampled_vouchers DROP COLUMN IF EXISTS voucher_date;
END $$;
