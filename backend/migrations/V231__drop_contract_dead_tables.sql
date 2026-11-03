-- V231: 删除死表 contracts / contract_extracted / contract_wp_link（Spec F FEAT-001 F1）。
--
-- 这三张表从 016 迁移起就有 ORM 模型与 service，但从未注册 router、从未被
-- 任何前端或后端代码在请求链路中使用。前端 ContractAnalysis* 组件已在候选树中删除，
-- 后端 contract_analysis_service.py 此次一并删除。表和枚举一起清理。
--
-- 真库三张表行数均为 0（2026-10-31 检查）。

-- 先删有外键引用的子表
DROP TABLE IF EXISTS contract_wp_link;
DROP TABLE IF EXISTS contract_extracted;
DROP TABLE IF EXISTS contracts;

-- 清理对应的 PG 枚举类型（clause_type_enum 保留：ai_analysis_item 表仍引用）
DROP TYPE IF EXISTS contract_type_enum;
DROP TYPE IF EXISTS contract_analysis_status_enum;
DROP TYPE IF EXISTS contract_link_type_enum;
