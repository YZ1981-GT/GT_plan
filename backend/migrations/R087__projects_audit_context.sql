-- R087: Rollback projects audit context columns

ALTER TABLE projects DROP COLUMN IF EXISTS is_large_soe;
ALTER TABLE projects DROP COLUMN IF EXISTS audit_type;
