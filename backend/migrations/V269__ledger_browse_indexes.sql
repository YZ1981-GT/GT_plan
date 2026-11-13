-- 序时账 / 辅助明细账「浏览全部科目」窗口索引：
--   (project_id, year, dataset_id, voucher_date, voucher_no, id) INCLUDE (debit_amount, credit_amount)
-- 既有 *_active_window 索引以 account_code 打头，不限科目时按日期排序用不上，只能全量排序；
-- 本索引让翻页走 keyset 范围扫描，月度汇总走仅索引扫描（实测 430 万行辅助明细：
-- 首屏 6.2s→1.7s，翻页 3.0s→0.02s）。
--
-- 大表请先并发预建（本迁移是事务性的，不能 CREATE INDEX CONCURRENTLY）：
--   python backend/scripts/ops/build_ledger_query_indexes.py --index ledger-browse --index aux-browse --apply --confirm BUILD_LEDGER_INDEXES
-- 纯性能索引：大表上缺索引时只给出提示、不阻断启动，查询结果不受影响（只是慢）。
DO $migration$
DECLARE
    spec record;
    index_valid boolean;
    row_estimate double precision;
BEGIN
    FOR spec IN
        SELECT * FROM (VALUES
            ('tb_ledger', 'idx_tb_ledger_active_browse'),
            ('tb_aux_ledger', 'idx_tb_aux_ledger_active_browse')
        ) AS t(table_name, index_name)
    LOOP
        SELECT i.indisvalid AND i.indisready
          INTO index_valid
          FROM pg_index i
          JOIN pg_class c ON c.oid = i.indexrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relname = spec.index_name;

        IF index_valid IS TRUE THEN
            CONTINUE;
        END IF;
        IF index_valid IS FALSE THEN
            RAISE NOTICE '% 存在但无效，请运行 build_ledger_query_indexes.py 重建', spec.index_name;
            CONTINUE;
        END IF;

        SELECT GREATEST(c.reltuples, 0) INTO row_estimate
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relname = spec.table_name;
        IF COALESCE(row_estimate, 0) > 100000 THEN
            RAISE NOTICE '% 行数估计 % 过大，未在迁移内建 %；请用 build_ledger_query_indexes.py 并发预建',
                spec.table_name, row_estimate, spec.index_name;
            CONTINUE;
        END IF;

        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.%I '
            '(project_id, year, dataset_id, voucher_date ASC NULLS LAST, voucher_no ASC NULLS LAST, id ASC) '
            'INCLUDE (debit_amount, credit_amount) WHERE is_deleted = false',
            spec.index_name, spec.table_name);
    END LOOP;
END
$migration$;
