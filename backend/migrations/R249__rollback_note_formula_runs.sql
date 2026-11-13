-- R249: 回滚 V249（原编号 V238，撞号后改为 V249）；执行前必须先回退附注公式运行代码。
DROP INDEX IF EXISTS idx_note_formula_run_project_year_section;
DROP TABLE IF EXISTS note_formula_run;
