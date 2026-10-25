-- R167：回滚 V167（合并企业树三码自动构建）
--
-- 🔴 回滚会丢失两列数据：projects.relation_to_parent（子公司/分公司关系）与
--    elimination_entries.branch_entity_code（分录归属的差额节点）。回滚后企业树退回
--    parent_project_id 口径，母分差额分录会失去归属 —— 回滚前请先导出这两列。
-- 顺序：先删依赖列的索引与约束，再删列。

DROP INDEX IF EXISTS ix_elim_entries_project_year_branch;
DROP INDEX IF EXISTS ix_projects_group_parent;

ALTER TABLE elimination_entries DROP COLUMN IF EXISTS branch_entity_code;

ALTER TABLE projects DROP CONSTRAINT IF EXISTS ck_projects_relation_to_parent;
ALTER TABLE projects DROP COLUMN IF EXISTS relation_to_parent;

COMMENT ON COLUMN projects.consolidation_type IS NULL;
COMMENT ON COLUMN consol_worksheet.node_company_code IS NULL;
