-- V032: PBC 证据收集体系增强
-- Spec: wp-evidence-collection
-- Requirements: 1.2 (PBC 关联底稿/审计循环), 3.3 (evidence_group 升级)

-- 1. pbc_checklist 新增关联字段
ALTER TABLE pbc_checklist ADD COLUMN IF NOT EXISTS wp_id UUID;
ALTER TABLE pbc_checklist ADD COLUMN IF NOT EXISTS cycle_code VARCHAR(10);
ALTER TABLE pbc_checklist ADD COLUMN IF NOT EXISTS category VARCHAR(100);
ALTER TABLE pbc_checklist ADD COLUMN IF NOT EXISTS due_date DATE;

CREATE INDEX IF NOT EXISTS idx_pbc_checklist_wp ON pbc_checklist(wp_id);
CREATE INDEX IF NOT EXISTS idx_pbc_checklist_cycle ON pbc_checklist(cycle_code);
CREATE INDEX IF NOT EXISTS idx_pbc_checklist_status ON pbc_checklist(project_id, status);
