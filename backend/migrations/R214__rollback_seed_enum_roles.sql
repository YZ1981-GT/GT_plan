-- R214: 回滚 V214（删除 seed 的角色记录）。
DELETE FROM sys_role WHERE role_key IN ('admin','partner','manager','site_lead','auditor','qc','eqcr','readonly');
