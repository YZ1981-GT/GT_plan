-- R020__rollback_note_dynamic_model.sql
-- 回滚 V020：移除动态模型相关表和字段。
--
-- 警告：回滚会丢失 group_note_template_baseline / note_section_version_tree 数据，
-- 仅在开发/测试环境使用。

BEGIN;

-- 3. 移除 note_section_version_tree 表
DROP INDEX IF EXISTS ix_version_tree_parent_node;
DROP INDEX IF EXISTS ix_version_tree_project_section;
DROP TABLE IF EXISTS note_section_version_tree;

-- 2. 移除 group_note_template_baseline 表
DROP INDEX IF EXISTS ix_group_baseline_parent_baseline;
DROP INDEX IF EXISTS ix_group_baseline_parent_project;
DROP TABLE IF EXISTS group_note_template_baseline;

-- 1. 移除 disclosure_notes 新增字段
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS text_template_vars;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS is_local_override;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS template_lineage;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS is_empty;

COMMIT;
