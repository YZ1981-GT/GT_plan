-- R169: 回滚 V169 公式推送引擎两张表
--
-- 删除后公式推送引擎失去「上次推送值」判据：可编辑目标无法区分「用户改过」与「引擎写的」，
-- 引擎必须停用（否则会覆盖人工录入）。两表只存推送派生状态，不含业务源数据。
-- 先删 state（引用 run），再删 run。
DROP INDEX IF EXISTS idx_formula_push_state_project_year_state;
DROP TABLE IF EXISTS formula_push_state;
DROP INDEX IF EXISTS idx_formula_push_run_project_year;
DROP TABLE IF EXISTS formula_push_run;
