-- R191: 回滚 V191（只删本迁移新增的 additive 列 / 索引；原 V189/R189 因撞号改至 191）
-- 注意：回滚会丢失 OO 陈旧底版留痕与回填文字基线，生产环境执行前须先导出相关列。

DROP INDEX IF EXISTS uq_word_export_versions_task_no;

ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS render_context;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS oo_doc_key;
ALTER TABLE word_export_task_versions DROP COLUMN IF EXISTS base_version_no;

ALTER TABLE deliverable_section_state DROP COLUMN IF EXISTS text_render_context;
ALTER TABLE deliverable_section_state DROP COLUMN IF EXISTS outside_hash;
ALTER TABLE deliverable_section_state DROP COLUMN IF EXISTS text_source_hash;
ALTER TABLE deliverable_section_state DROP COLUMN IF EXISTS text_baseline;

ALTER TABLE working_paper DROP COLUMN IF EXISTS procedure_completion_rate;
ALTER TABLE working_paper DROP COLUMN IF EXISTS quality_score;
