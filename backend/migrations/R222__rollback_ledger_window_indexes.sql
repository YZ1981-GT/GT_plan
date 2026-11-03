-- On a populated live database prefer the concurrent operations tool:
--   python backend/scripts/ops/build_ledger_query_indexes.py --index ledger-window --index aux-window --drop --apply --confirm DROP_LEDGER_INDEXES
DROP INDEX IF EXISTS public.idx_tb_aux_ledger_active_window;
DROP INDEX IF EXISTS public.idx_tb_ledger_active_window;
