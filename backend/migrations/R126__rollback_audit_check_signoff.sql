-- R126: 回滚 V126（审计检查复核门禁签认）
-- 默认仅 drop 索引（保表保数据，避免丢失签认留痕）。

-- 如需彻底回滚（会丢失全部签认记录），取消注释：
-- DROP TABLE IF EXISTS audit_check_signoff;

DROP INDEX IF EXISTS idx_audit_check_signoff_proj_year;
