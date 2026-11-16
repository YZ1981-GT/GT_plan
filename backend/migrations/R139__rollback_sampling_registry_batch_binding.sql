-- R139: 回滚 V139（抽样批次绑定列）。
DO $$
BEGIN
    IF to_regclass('public.sampling_records') IS NOT NULL
       AND EXISTS (SELECT 1 FROM sampling_records WHERE batch_id IS NOT NULL OR sampling_method IS NOT NULL OR random_seed IS NOT NULL OR dataset_id IS NOT NULL) THEN
        RAISE EXCEPTION 'R139 拒绝回滚：sampling_records 已保存批次/数据集事实';
    END IF;
    IF to_regclass('public.sampled_vouchers') IS NOT NULL
       AND EXISTS (SELECT 1 FROM sampled_vouchers WHERE batch_id IS NOT NULL) THEN
        RAISE EXCEPTION 'R139 拒绝回滚：sampled_vouchers 已绑定批次';
    END IF;
END $$;
DROP INDEX IF EXISTS uq_sampled_vouchers_batch;
DROP INDEX IF EXISTS ix_sampled_vouchers_project_voucher;
DROP INDEX IF EXISTS ix_sampling_records_project_wp;
DROP INDEX IF EXISTS ix_sampling_records_batch;
ALTER TABLE sampled_vouchers DROP COLUMN IF EXISTS batch_id;
ALTER TABLE sampling_records DROP COLUMN IF EXISTS dataset_id;
ALTER TABLE sampling_records DROP COLUMN IF EXISTS random_seed;
ALTER TABLE sampling_records DROP COLUMN IF EXISTS sampling_method;
ALTER TABLE sampling_records DROP COLUMN IF EXISTS batch_id;
