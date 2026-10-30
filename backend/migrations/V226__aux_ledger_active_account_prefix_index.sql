-- Pre-deploy on populated databases:
--   python backend/scripts/ops/build_ledger_query_indexes.py --apply --confirm BUILD_LEDGER_INDEXES
-- MigrationRunner is transactional, so it cannot safely CREATE INDEX CONCURRENTLY.
DO $migration$
DECLARE
    row_estimate double precision;
    index_valid boolean;
BEGIN
    SELECT i.indisvalid AND i.indisready
      INTO index_valid
      FROM pg_index i
      JOIN pg_class c ON c.oid = i.indexrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname = 'idx_tb_aux_ledger_active_account_prefix';

    IF index_valid IS TRUE THEN
        RETURN;
    END IF;
    IF index_valid IS FALSE THEN
        RAISE EXCEPTION 'idx_tb_aux_ledger_active_account_prefix exists but is invalid; run the concurrent index tool';
    END IF;

    SELECT GREATEST(c.reltuples, 0) INTO row_estimate
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = 'tb_aux_ledger';
    IF COALESCE(row_estimate, 0) > 100000 THEN
        RAISE EXCEPTION 'large tb_aux_ledger requires concurrent prebuild; estimated rows=%', row_estimate;
    END IF;

    CREATE INDEX IF NOT EXISTS idx_tb_aux_ledger_active_account_prefix
        ON public.tb_aux_ledger
        (project_id, year, dataset_id, account_code text_pattern_ops)
        WHERE is_deleted = false;
END
$migration$;