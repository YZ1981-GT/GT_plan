-- Ledger windows use a stable keyset order.  Build these indexes concurrently on
-- populated systems before this transactional runtime migration is applied:
--   python backend/scripts/ops/build_ledger_query_indexes.py --index ledger-window --index aux-window --apply --confirm BUILD_LEDGER_INDEXES
--
-- The runtime migration does not issue CREATE INDEX CONCURRENTLY.  It verifies
-- the concurrent prebuild on a large database, while allowing a small fresh
-- database to create the same indexes transactionally.
DO $migration$
DECLARE
    spec record;
    row_estimate double precision;
    index_valid boolean;
BEGIN
    FOR spec IN
        SELECT * FROM (VALUES
            ('tb_ledger', 'idx_tb_ledger_active_window',
             'CREATE INDEX IF NOT EXISTS idx_tb_ledger_active_window ON public.tb_ledger (project_id, year, dataset_id, account_code, voucher_date ASC NULLS LAST, voucher_no ASC NULLS LAST, id ASC) WHERE is_deleted = false'),
            ('tb_aux_ledger', 'idx_tb_aux_ledger_active_window',
             'CREATE INDEX IF NOT EXISTS idx_tb_aux_ledger_active_window ON public.tb_aux_ledger (project_id, year, dataset_id, account_code, aux_type, aux_code, voucher_date ASC NULLS LAST, voucher_no ASC NULLS LAST, id ASC) WHERE is_deleted = false')
        ) AS planned(table_name, index_name, create_sql)
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
            RAISE EXCEPTION '% exists but is invalid; run build_ledger_query_indexes.py', spec.index_name;
        END IF;
        SELECT GREATEST(c.reltuples, 0) INTO row_estimate
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relname = spec.table_name;
        IF COALESCE(row_estimate, 0) > 100000 THEN
            RAISE EXCEPTION 'large % requires concurrent prebuild of %; estimated rows=%',
                spec.table_name, spec.index_name, row_estimate;
        END IF;
        EXECUTE spec.create_sql;
    END LOOP;
END
$migration$;
