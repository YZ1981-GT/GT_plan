-- V019__add_note_section_id_columns.sql
-- D13 章节序号重构基础迁移（Sprint A.0.1）
--
-- 给 disclosure_notes 加 7 列 + 2 索引，支撑 section_id / level / parent_section_id 树形结构
-- 与自动编号 / 用户锁定序号机制。
--
-- 注意事项：
--   * section_id / level / parent_section_id 此版本保持 nullable=true；
--     A.0.5 一次性迁移脚本 backfill 完成后，下一版迁移再收紧为 NOT NULL。
--   * note_section（旧字符串字段）作为 legacy compat 保留，不在本迁移删除。
--   * 全部 ALTER 用 IF NOT EXISTS / DO 块包裹，遵循 D6 idempotent 原则，可重复执行。
--   * 虽然原任务命名 V022，因当前 V001-V018 已落地，按真实下一编号取 V019。

BEGIN;

-- 1. section_id：稳定 ID，跨年保持不变；A.0.5 backfill 后转 NOT NULL
ALTER TABLE disclosure_notes
    ADD COLUMN IF NOT EXISTS section_id VARCHAR(100) NULL;

-- 2. level：层级 1-5（一/(一)/1./(1)/①）
ALTER TABLE disclosure_notes
    ADD COLUMN IF NOT EXISTS level SMALLINT NULL;

-- 2b. level 范围 CHECK（PG 不支持 ADD CONSTRAINT IF NOT EXISTS，用 DO 块兜底）
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

-- 3. parent_section_id：树形父引用（非外键，避免跨项目/年度环境下的级联复杂度）
ALTER TABLE disclosure_notes
    ADD COLUMN IF NOT EXISTS parent_section_id VARCHAR(100) NULL;

-- 4. sort_index：同层级内排序，默认 0
ALTER TABLE disclosure_notes
    ADD COLUMN IF NOT EXISTS sort_index INTEGER NULL DEFAULT 0;

-- 5. auto_numbering：是否参与自动编号
ALTER TABLE disclosure_notes
    ADD COLUMN IF NOT EXISTS auto_numbering BOOLEAN NOT NULL DEFAULT true;

-- 6. lock_number：用户是否锁定该章节序号（不参与重排）
ALTER TABLE disclosure_notes
    ADD COLUMN IF NOT EXISTS lock_number BOOLEAN NOT NULL DEFAULT false;

-- 7. locked_number：用户锁定时显示的固定序号字符串（如 "五、(三) 2."）
ALTER TABLE disclosure_notes
    ADD COLUMN IF NOT EXISTS locked_number VARCHAR(50) NULL;

-- 8. 索引：按 (project_id, year, section_id) 快速定位章节（A.0.3 numbering service 用）
CREATE INDEX IF NOT EXISTS ix_disclosure_notes_project_year_section_id
    ON disclosure_notes (project_id, year, section_id);

-- 9. 索引：按 parent_section_id 树遍历
CREATE INDEX IF NOT EXISTS ix_disclosure_notes_parent_section_id
    ON disclosure_notes (parent_section_id);

COMMIT;
