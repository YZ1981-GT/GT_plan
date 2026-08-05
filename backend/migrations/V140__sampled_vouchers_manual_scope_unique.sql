-- V140: 把 sampled_vouchers 的旧唯一索引收窄到「手工标记」范围
--       （sampling-compliance-closure Wave 2，修正 V139 的设计输入缺陷）
--
-- 问题（2026-08-04 应用 V139 后实测发现）：
--   既有索引 uq_sampled_voucher_project_year_no 是
--     UNIQUE (project_id, year, voucher_no) WHERE is_deleted = false
--   即「同一项目同一年度同一凭证号全库只能有一行」。两个后果：
--   1) 抽凭引擎登记时会撞该索引抛 UniqueViolation（V139 新索引声明的 on_conflict
--      目标是五列索引，撞另一个唯一索引不会 DO NOTHING）→ 登记除首次外全部失败，
--      且被 fail-open 吞成 WARNING；
--   2) 更根本：「同一凭证被多个底稿重复抽取」这一**需要被发现的事实**在数据层
--      不可表达 → 项目级重复抽凭检测（voucher-coverage 的 duplicated）永远为空。
--
-- 处置：**放宽而非收紧**（不删数据、不改既有行）。
--   - 旧索引语义对**手工标记**（ledger_penetration 穿透页点「抽中本凭证」，
--     batch_id IS NULL）是合理的：同一凭证手工标记两次无意义 → 保留该约束，
--     但加上 batch_id IS NULL 条件，只管手工侧。
--   - 抽凭引擎登记（batch_id 非空）由 V139 的 uq_sampled_vouchers_batch 约束：
--     同批次同凭证唯一，**不同批次的同一凭证允许共存**。
--
-- 兼容性：改造前全库 sampled_vouchers 仅 1 行（手工标记，batch_id 为 NULL），
-- 放宽后该行仍受新的部分索引约束，既有数据零违规、零变更。
--
-- 幂等：DROP IF EXISTS + CREATE IF NOT EXISTS，可重复执行。

DROP INDEX IF EXISTS uq_sampled_voucher_project_year_no;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sampled_voucher_manual_project_year_no
  ON sampled_vouchers (project_id, year, voucher_no)
  WHERE is_deleted = false AND batch_id IS NULL;

COMMENT ON INDEX uq_sampled_voucher_manual_project_year_no IS
  '手工标记（batch_id IS NULL，来自 ledger_penetration 穿透页）的凭证去重；'
  '抽凭引擎登记走 uq_sampled_vouchers_batch 按批次唯一';
