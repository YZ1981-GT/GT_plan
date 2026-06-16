-- V083: 统一 tb_aux_balance_summary 列名为 dim_type（幂等）
-- 根因：代码（查询端 ledger_penetration + 写入端 smart_import_engine）和前端 API 参数
-- 均使用 dim_type，但建表时列名为 aux_type，导致反复来回改代码不如一次性统一 schema。
-- 源表 tb_aux_balance 的列保持 aux_type 不动（SELECT 时 ab.aux_type 作为值写入 dim_type 列）。

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'tb_aux_balance_summary' AND column_name = 'aux_type'
    ) THEN
        ALTER TABLE tb_aux_balance_summary RENAME COLUMN aux_type TO dim_type;
    END IF;
END $$;
