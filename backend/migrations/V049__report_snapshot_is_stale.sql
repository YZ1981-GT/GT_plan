-- V049: report_snapshot 加 is_stale 列（QC-25 报表快照过期门禁依赖）
-- 背景：gate_rules_phase14 QC-25 规则查 report_snapshots.is_stale 判断报表快照是否过期，
--   但 ①表名拼写错（真实表是单数 report_snapshot）②真实表无 is_stale 列。
--   QC-25 曾用 to_regclass 守卫静默跳过（功能空壳）。本迁移补 is_stale 列，
--   配合 QC-25 改正表名后该门禁真正生效（与 disclosure_notes/financial_report/
--   report_config 的 is_stale stale 传播机制一致）。

ALTER TABLE report_snapshot
    ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT false;
