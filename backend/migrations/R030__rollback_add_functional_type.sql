-- R030: 回滚 functional_type 列
DROP INDEX IF EXISTS idx_wpsc_functional_type;
ALTER TABLE workpaper_sheet_classification DROP COLUMN IF EXISTS functional_type;
