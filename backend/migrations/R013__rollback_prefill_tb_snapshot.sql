-- R013__rollback_prefill_tb_snapshot.sql
-- 回滚 V013__add_prefill_tb_snapshot.sql
-- 删除 working_paper 表的 prefill_tb_snapshot 列

ALTER TABLE working_paper
    DROP COLUMN IF EXISTS prefill_tb_snapshot;
