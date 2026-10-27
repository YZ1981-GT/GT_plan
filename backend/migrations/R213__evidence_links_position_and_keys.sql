-- R213: 回滚 V213 —— 去掉本迁移起名的外键与组合索引，cell_ref 改回 20。
-- idx_evidence_wp / idx_evidence_attachment 是 ORM 声明的索引（V213 用 IF NOT EXISTS 补），回滚不删。
-- 已有超过 20 字的 cell_ref（item:/row: 位置）时最后一句会失败：先处理这些行再回滚，不截断数据。
DROP INDEX IF EXISTS idx_evidence_links_position;
ALTER TABLE evidence_links DROP CONSTRAINT IF EXISTS fk_evidence_links_attachment;
ALTER TABLE evidence_links DROP CONSTRAINT IF EXISTS fk_evidence_links_wp;
ALTER TABLE evidence_links ALTER COLUMN cell_ref TYPE VARCHAR(20);
