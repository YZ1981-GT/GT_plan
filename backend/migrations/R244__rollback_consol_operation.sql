-- R240：回滚持久合并运行根记录。

DROP INDEX IF EXISTS ix_consol_push_run_operation;
ALTER TABLE consol_push_run DROP COLUMN IF EXISTS operation_id;

DROP INDEX IF EXISTS ix_consol_operation_claim;
DROP INDEX IF EXISTS ix_consol_operation_project_year;
DROP INDEX IF EXISTS ux_consol_operation_queued;
DROP INDEX IF EXISTS ux_consol_operation_running;
DROP INDEX IF EXISTS ux_consol_operation_idempotency;
DROP TABLE IF EXISTS consol_operation;
