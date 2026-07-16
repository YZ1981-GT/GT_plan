-- V109: 冻结七值 SystemRole — 补入独立 EQCR 角色到 DB 角色 enum
-- Spec: attachment-ocr-ai-evidence-governance-hardening / Task 1.1（Wave 0 冻结 P0 契约）
-- 设计 §2.1：实施第一步须对齐后端 SystemRole 枚举、DB 角色 enum、JWT、ProjectAssignment 映射；
--            发现漂移必须先修正并以契约测试锁定，之后才允许迁移治理模型。
--
-- 漂移事实（实测）：
--   * PG enum `userrole`        = 6 值（缺 eqcr）——应为七值 admin/partner/manager/auditor/qc/eqcr/readonly
--   * PG enum `projectuserrole` = 5 值（缺 eqcr）——eqcr 是独立合法项目角色
--   ORM 侧 UserRole / ProjectUserRole 已同步补入 eqcr（backend/app/models/base.py）。
--
-- 本迁移为 additive + 幂等（ADD VALUE IF NOT EXISTS）。PG12+/PG16 允许在事务块内
-- ADD VALUE（新值仅不能在同一事务内被使用）；本迁移不使用该值，故 migration_runner 的
-- 单事务执行方式安全。enum 值一经加入不可移除（见 R109 回滚说明）。
--
-- 单一真源：app.services.evidence_governance.role_capability_contract.SYSTEM_ROLES

ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'eqcr';

ALTER TYPE projectuserrole ADD VALUE IF NOT EXISTS 'eqcr';
