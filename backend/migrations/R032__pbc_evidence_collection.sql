-- R032: 回滚 PBC 证据收集体系增强
DROP INDEX IF EXISTS idx_pbc_checklist_wp;
DROP INDEX IF EXISTS idx_pbc_checklist_cycle;
DROP INDEX IF EXISTS idx_pbc_checklist_status;

ALTER TABLE pbc_checklist DROP COLUMN IF EXISTS wp_id;
ALTER TABLE pbc_checklist DROP COLUMN IF EXISTS cycle_code;
ALTER TABLE pbc_checklist DROP COLUMN IF EXISTS category;
ALTER TABLE pbc_checklist DROP COLUMN IF EXISTS due_date;
