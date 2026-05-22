-- V007: 审计日志表设置 append-only（SC-1 安全加固）
-- 撤销普通用户对 audit_log 表的 DELETE 和 UPDATE 权限
-- 仅 superuser 可修改（用于紧急修复场景）

-- 注意：此迁移假设应用使用的 DB 用户不是 superuser
-- 如果应用用户是 postgres superuser，此迁移无实际效果（需要创建独立应用用户）

REVOKE DELETE ON TABLE audit_log FROM PUBLIC;
REVOKE UPDATE ON TABLE audit_log FROM PUBLIC;

-- 添加注释标记此表为 append-only
COMMENT ON TABLE audit_log IS 'Append-only audit trail. DELETE/UPDATE revoked for non-superuser roles (SC-1).';
