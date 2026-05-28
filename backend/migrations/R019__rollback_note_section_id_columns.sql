-- R019__rollback_note_section_id_columns.sql
-- 回滚 V019：移除 disclosure_notes 上的 7 列 + 2 索引 + 1 CHECK 约束。
--
-- 警告：回滚会丢失 A.0.5 backfill 的 section_id 数据，仅在开发/测试环境使用。

BEGIN;

DROP INDEX IF EXISTS ix_disclosure_notes_parent_section_id;
DROP INDEX IF EXISTS ix_disclosure_notes_project_year_section_id;

ALTER TABLE disclosure_notes
    DROP CONSTRAINT IF EXISTS ck_disclosure_notes_level_range;

ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS locked_number;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS lock_number;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS auto_numbering;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS sort_index;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS parent_section_id;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS level;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS section_id;

COMMIT;
