-- V214: 把 UserRole 枚举的 8 个值 seed 成 sys_role 记录（权限中心对齐）
-- 对应参考 V156 移植 + 当前项目 UserRole 有 site_lead（8 值）故补 seed。
--
-- 目的：让「未在 sys_user_role 建立任何绑定」的历史账号，仍能依据其 users.role
--   枚举值对应的 seed 角色解析出确定的 data_scope —— 否则旧账号落到「无角色 ⇒
--   回退仅本人」，而 admin 会因此看不到任何项目。
-- data_scope：admin/partner = 1（全部）；其余 6 个 = 5（仅本人，后续可调）。
-- 幂等：INSERT ... WHERE NOT EXISTS 逐行判存，可重复执行不报错。

INSERT INTO sys_role (name, role_key, data_scope, status)
SELECT '系统管理员', 'admin', 1, '0'
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'admin' AND is_deleted = false);

INSERT INTO sys_role (name, role_key, data_scope, status)
SELECT '合伙人', 'partner', 1, '0'
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'partner' AND is_deleted = false);

INSERT INTO sys_role (name, role_key, data_scope, status)
SELECT '项目经理', 'manager', 5, '0'
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'manager' AND is_deleted = false);

INSERT INTO sys_role (name, role_key, data_scope, status)
SELECT '现场经理', 'site_lead', 5, '0'
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'site_lead' AND is_deleted = false);

INSERT INTO sys_role (name, role_key, data_scope, status)
SELECT '审计人员', 'auditor', 5, '0'
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'auditor' AND is_deleted = false);

INSERT INTO sys_role (name, role_key, data_scope, status)
SELECT '质量控制', 'qc', 5, '0'
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'qc' AND is_deleted = false);

INSERT INTO sys_role (name, role_key, data_scope, status)
SELECT '项目质量复核', 'eqcr', 5, '0'
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'eqcr' AND is_deleted = false);

INSERT INTO sys_role (name, role_key, data_scope, status)
SELECT '只读用户', 'readonly', 5, '0'
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'readonly' AND is_deleted = false);

-- admin / partner 的 data_scope 恒为 1（收敛式修正，防人为改成 5 后重跑迁移不生效）
UPDATE sys_role
SET data_scope = 1, updated_at = now()
WHERE role_key IN ('admin', 'partner')
  AND is_deleted = false
  AND data_scope <> 1;
