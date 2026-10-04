-- R179__rollback_repair_v019_disclosure_notes_constraint_and_indexes.sql
-- 回滚 V179：删除补齐的 2 个索引 + 1 个 CHECK 约束（即 R019 的子集，仅针对本迁移补齐的对象）。

DROP INDEX IF EXISTS ix_disclosure_notes_parent_section_id;
DROP INDEX IF EXISTS ix_disclosure_notes_project_year_section_id;

ALTER TABLE disclosure_notes
    DROP CONSTRAINT IF EXISTS ck_disclosure_notes_level_range;
