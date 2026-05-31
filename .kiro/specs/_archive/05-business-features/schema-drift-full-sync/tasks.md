# Tasks — Schema Drift Full Sync

## Task List

- [x] 1. Write introspection script `backend/scripts/gen/gen_schema_sync_migration.py`
- [x] 2. Run script to generate `V033__sync_schema_columns.sql`
- [x] 3. Apply the migration to local PG
- [-] 4. Verify: health endpoint reports 0 critical orm_extra drifts
