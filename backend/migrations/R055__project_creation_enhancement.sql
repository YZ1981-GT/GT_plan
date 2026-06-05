-- R055__project_creation_enhancement.sql (Rollback)
DROP INDEX IF EXISTS uq_project_company_year_scope;
ALTER TABLE projects DROP COLUMN IF EXISTS short_name;
ALTER TABLE projects DROP COLUMN IF EXISTS audit_year;
