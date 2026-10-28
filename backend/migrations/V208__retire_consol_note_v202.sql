-- V208: 退役 V202（合并附注映射规则模板库 / 值确认 / 结构锁）
-- spec: note-pull-followup-closure R16
--
-- V202 的四张表没有界面、没有生效的消费方（结构锁按合并章节号存、子企业按单体章节号查，恒查不到；值确认只被自己的
-- 就绪检查端点读；规则模板库只被已删的提升端点写），路由 / 服务 / 模型已删除。子企业保存后合并附注标「待更新」改走
-- consol_note_data.is_stale（与 V202 无关，保留）。
-- 回滚：R208（按 V202 原样重建，数据不恢复；删表前的行备份见 backend/backups/）。

-- 先删引用规则模板库的列（外键随列一起删）
ALTER TABLE consol_note_mapping_rule
    DROP COLUMN IF EXISTS promoted_to_template_id;

-- 按依赖反序删表（索引随表删除）
DROP TABLE IF EXISTS consol_note_value_confirmation;
DROP TABLE IF EXISTS consol_note_structure_lock_entity;
DROP TABLE IF EXISTS consol_note_structure_lock;
DROP TABLE IF EXISTS consol_note_mapping_rule_template;
