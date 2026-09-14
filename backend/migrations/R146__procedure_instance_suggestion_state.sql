-- R146: 回滚 V146（procedure_instances.suggestion_state）
--
-- Spec: procedure-trimming-and-delegation-intelligence — Wave 2 Task 11
--
-- ⚠️ 回滚会丢弃全部裁剪建议态与驳回留痕（`rejected` / `rejected_by` / `rejected_at`）。
--    已确认落库的裁剪状态本身在 `procedure_instances.status` 与 `skip_reason`，
--    不受本回滚影响 —— 即回滚后裁剪结果仍在，只是「哪条是系统建议的」与
--    「审计师驳回过哪些」两类留痕消失，且被驳回过的程序会重新进入智能裁剪建议。

ALTER TABLE procedure_instances DROP COLUMN IF EXISTS suggestion_state;
