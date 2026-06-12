-- R070: Rollback for V070 (bad_debt_detail_rows)
-- 顺序：先删索引，后删表（表删除会自动级联删除其上的索引，但显式先删保证幂等清晰）

DROP INDEX IF EXISTS uq_bad_debt_provision_method;
DROP INDEX IF EXISTS ix_bad_debt_rows_parent;
DROP INDEX IF EXISTS ix_bad_debt_rows_wp_index;

DROP TABLE IF EXISTS bad_debt_detail_rows;
