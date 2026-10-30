-- R221: 回滚 V221 — 删链尾表与两个索引

DROP TABLE IF EXISTS audit_chain_head;
DROP INDEX IF EXISTS idx_audit_log_entries_prev_hash;
DROP INDEX IF EXISTS idx_audit_log_entries_chain;
