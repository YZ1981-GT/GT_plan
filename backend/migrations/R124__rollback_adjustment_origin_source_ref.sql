-- R124: 回滚 V124（adjustments origin / source_ref）
-- 安全回滚：drop 索引；additive 列默认保留（不删数据以防丢失底稿汇聚溯源）。

DROP INDEX IF EXISTS idx_adjustments_source_ref;

-- 如需彻底回滚列（会丢失 origin 分类与底稿溯源），取消注释：
-- ALTER TABLE adjustments DROP COLUMN IF EXISTS source_ref;
-- ALTER TABLE adjustments DROP COLUMN IF EXISTS origin;
