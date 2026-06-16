-- R085: Rollback checklist_responses table
DROP INDEX IF EXISTS idx_checklist_resp_wp;
DROP INDEX IF EXISTS idx_checklist_resp_project;
DROP TABLE IF EXISTS checklist_responses;
