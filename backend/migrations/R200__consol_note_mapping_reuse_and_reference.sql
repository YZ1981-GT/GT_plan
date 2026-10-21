-- R200: 回滚 V200（合并附注映射规则复用与标准科目参考下推）

-- 先删 FK 列（必须在删引用表之前）
ALTER TABLE consol_note_mapping_rule
    DROP COLUMN IF EXISTS promoted_to_template_id;

-- 按依赖反序删表
DROP TABLE IF EXISTS consol_note_value_confirmation;
DROP TABLE IF EXISTS consol_note_structure_lock_entity;
DROP TABLE IF EXISTS consol_note_structure_lock;
DROP TABLE IF EXISTS consol_note_mapping_rule_template;
