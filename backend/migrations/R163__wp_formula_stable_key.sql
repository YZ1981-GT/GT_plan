-- R163: 回滚 wp_formula 稳定键三列 + 新索引
--
-- 删除新索引与三列 + needs_review 标记列。旧 identity (wp_id, sheet_name, target_cell)
-- 与旧唯一索引 uq_wp_formula_wp_sheet_cell 一直保留未动，回滚后系统回到纯旧键，无数据丢失
-- （稳定键为派生列，可由 V163 回填逻辑重新推导）。

DROP INDEX IF EXISTS uq_wp_formula_stable_key;

ALTER TABLE wp_formula
    DROP COLUMN IF EXISTS stable_sheet_key,
    DROP COLUMN IF EXISTS row_key,
    DROP COLUMN IF EXISTS field_key,
    DROP COLUMN IF EXISTS stable_key_needs_review;
