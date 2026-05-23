-- V013__add_prefill_tb_snapshot.sql
-- L-3 一致性快照告警（spec proposal-remaining-18 task 2.3）
-- working_paper 表新增 prefill_tb_snapshot JSONB 字段
-- 内容形如 {"account_code": audited_amount}，每次 prefill 执行后写入
-- 下次 prefill 时对比当前 TB 值与快照，差异 > 0 标记 cell 为 stale_since_last_prefill

ALTER TABLE working_paper
    ADD COLUMN IF NOT EXISTS prefill_tb_snapshot JSONB;

COMMENT ON COLUMN working_paper.prefill_tb_snapshot
    IS 'L-3 一致性快照：上次 prefill 时涉及账户的 TB audited_amount 映射 {account_code: amount}';
