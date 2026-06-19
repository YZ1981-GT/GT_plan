-- Rollback V083: 恢复列名 dim_type → aux_type
DO $
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'tb_aux_balance_summary' AND column_name = 'dim_type'
    ) THEN
        ALTER TABLE tb_aux_balance_summary RENAME COLUMN dim_type TO aux_type;
    END IF;
END $;
