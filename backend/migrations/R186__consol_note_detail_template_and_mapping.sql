-- R186: 回滚 V186 合并附注明细模板与多企业行映射规则
-- 按创建反序 DROP（先子表后父表，避免外键约束阻塞）

DROP TABLE IF EXISTS consol_note_mapping_binding;
DROP TABLE IF EXISTS consol_note_mapping_rule;
DROP TABLE IF EXISTS consol_note_template_binding;
DROP TABLE IF EXISTS consol_note_detail_template_version;
DROP TABLE IF EXISTS consol_note_detail_template;
