-- V007: 审计日志表设置 append-only（SC-1 安全加固）
-- 撤销普通用户对 audit_log 表的 DELETE 和 UPDATE 权限
-- 仅 superuser 可修改（用于紧急修复场景）
-- 使用 IF EXISTS 避免表不存在时报错

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_log') THEN
    EXECUTE 'REVOKE DELETE ON TABLE audit_log FROM PUBLIC';
    EXECUTE 'REVOKE UPDATE ON TABLE audit_log FROM PUBLIC';
    EXECUTE 'COMMENT ON TABLE audit_log IS ''Append-only audit trail. DELETE/UPDATE revoked for non-superuser roles (SC-1).''';
  END IF;
END $$;
