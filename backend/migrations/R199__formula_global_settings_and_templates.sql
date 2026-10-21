-- R199: 回滚 V199 —— 删除公式全局设置 / 模板相关表与加列（报表与底稿公式本身保留）。
DROP TABLE IF EXISTS formula_template_subscription;
DROP TABLE IF EXISTS formula_publish;
DROP TABLE IF EXISTS formula_sync_item;
DROP TABLE IF EXISTS formula_setting;
DROP TABLE IF EXISTS formula_template_version;
DROP TABLE IF EXISTS formula_template;
ALTER TABLE consol_note_formula DROP COLUMN IF EXISTS version;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS base_template_id;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS base_origin;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS pinned;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS base_definition;
ALTER TABLE wp_formula DROP COLUMN IF EXISTS base_version;
ALTER TABLE report_config DROP COLUMN IF EXISTS base_template_id;
ALTER TABLE report_config DROP COLUMN IF EXISTS base_origin;
ALTER TABLE report_config DROP COLUMN IF EXISTS pinned;
ALTER TABLE report_config DROP COLUMN IF EXISTS base_definition;
ALTER TABLE report_config DROP COLUMN IF EXISTS base_version;
ALTER TABLE report_config DROP COLUMN IF EXISTS formula_version;
