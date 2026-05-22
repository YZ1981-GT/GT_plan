-- R007: 回滚审计日志 append-only 限制
GRANT DELETE ON TABLE audit_log TO PUBLIC;
GRANT UPDATE ON TABLE audit_log TO PUBLIC;
COMMENT ON TABLE audit_log IS NULL;
