-- R004__rollback_add_review_priority.sql
-- 回滚 V004__add_review_priority.sql
-- 删除 review_records 表的 priority 列、约束和索引

-- 删除索引（IF EXISTS 保证幂等）
DROP INDEX IF EXISTS idx_review_records_priority;

-- 删除约束（IF EXISTS 保证幂等）
ALTER TABLE review_records DROP CONSTRAINT IF EXISTS chk_review_priority;

-- 删除列（IF EXISTS 保证幂等）
ALTER TABLE review_records DROP COLUMN IF EXISTS priority;
