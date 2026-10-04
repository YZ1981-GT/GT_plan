-- V179__repair_v019_disclosure_notes_constraint_and_indexes.sql
-- 补齐 V019 缺失的 CHECK 约束 ck_disclosure_notes_level_range + 2 个索引。
--
-- 背景（见 checksum-drift-8 调查报告）：
--   V019 版本槽原本是 seed_workpaper_template_version（已重编号至 V038），磁盘文件被替换为
--   add_note_section_id_columns。因版本号 019 已登记为「已应用」，新文件内容从未由 runner 执行。
--   新文件声明的 7 个列已由 V051 的同样 ADD COLUMN 落库（存在），但 CHECK 约束
--   ck_disclosure_notes_level_range 与 2 个索引 ix_disclosure_notes_project_year_section_id /
--   ix_disclosure_notes_parent_section_id 仍缺失。
--   本迁移按 V019__add_note_section_id_columns.sql 现声明字节一致地补齐这三个对象。
--
-- 补约束前已确认无越界 level 数据：
--   SELECT count(*) FROM disclosure_notes WHERE level IS NOT NULL AND level NOT BETWEEN 1 AND 5;  => 0

-- 1. level 范围 CHECK（PG 不支持 ADD CONSTRAINT IF NOT EXISTS，用 DO 块兜底）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_disclosure_notes_level_range'
    ) THEN
        ALTER TABLE disclosure_notes
            ADD CONSTRAINT ck_disclosure_notes_level_range
            CHECK (level IS NULL OR (level BETWEEN 1 AND 5));
    END IF;
END
$$;

-- 2. 索引：按 (project_id, year, section_id) 快速定位章节（numbering service 用）
CREATE INDEX IF NOT EXISTS ix_disclosure_notes_project_year_section_id
    ON disclosure_notes (project_id, year, section_id);

-- 3. 索引：按 parent_section_id 树遍历
CREATE INDEX IF NOT EXISTS ix_disclosure_notes_parent_section_id
    ON disclosure_notes (parent_section_id);
