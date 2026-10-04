-- R172：回滚 V172（合并抵销分录单源与差额表推送）
--
-- 🔴 回滚会丢失：分录来源（origin / origin_key，由工作底稿生成的草稿失去来源键后重复生成会重复入账）、
--    推送运行记录、合并附注单元格公式（人工维护的公式需先导出）、附注待更新标记。
-- 顺序：先删索引，再删表与列。
DROP INDEX IF EXISTS ux_elim_entries_origin;
ALTER TABLE elimination_entries DROP COLUMN IF EXISTS origin_key;
ALTER TABLE elimination_entries DROP COLUMN IF EXISTS origin;
DROP INDEX IF EXISTS idx_consol_push_run_project_year;
DROP TABLE IF EXISTS consol_push_run;
DROP INDEX IF EXISTS ux_consol_note_formula_cell;
DROP TABLE IF EXISTS consol_note_formula;
ALTER TABLE consol_note_data DROP COLUMN IF EXISTS is_stale;
