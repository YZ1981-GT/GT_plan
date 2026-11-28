-- R274: 回滚 V274（旧式 doc key / callback drain ledger）
--
-- 本表是 4.2 新增的独立表，无其他表引用（除自引用 issuance_id）。
-- DROP 会连带删除 4 个索引与 6 个 CHECK 约束。
DROP TABLE IF EXISTS working_paper_legacy_drain_ledger;
