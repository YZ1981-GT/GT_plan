# Task 5 — executor 固定顺序与步骤依赖（交付证据）

> spec `chain-closure-phase4-deliverable-center-trio`，需求 2.1–2.6, 4.4。
> 分支 `work/2026-10-01-i-cycle-classification-convergence`，基线 HEAD `19c65589d`。

## 一、改了什么

### 1. 权威 `TRIO_STEPS`（单一真源，禁第三份分叉）
`backend/app/services/full_deliverables_executor.py`：

- 新增 `TRIO_STEPS: tuple[TrioStep, ...]`，固定顺序
  `financial_report(1) → disclosure_notes(2) → audit_report(3)`。
  每个 `TrioStep` 带 `key / sequence / doc_type / depends_on`。
- **稳定键只有一处定义**：从 `deliverable_trio_snapshot.TRIO_STEP_KEYS` 导入，
  模块 import 期 `assert tuple(s.key for s in TRIO_STEPS) == tuple(TRIO_STEP_KEYS)`。
  任何改名/漏项/调序立即在 import 期炸。readiness service 复用的也是同一个
  `TRIO_STEP_KEYS`，三处（executor / snapshot / readiness）共用一份键，不各写一份。
- `audit_report` 稳定键复用现有 `_run_report_body` 渲染路径（doc_type 仍 `audit_report`），
  不新造报告正文逻辑。
- `AUXILIARY_STEP_KEYS = ("financial_report_unadjusted",)`：辅助项显式登记，
  **不在** `TRIO_STEPS`、不计入正式完成数、不进成功 gate。
- `BLOCKED_BY_DEPENDENCY = "blocked_by_dependency"`：模块常量，作为 item 状态值
  （`status` 列是自由 String，可承载；它不是 `ExportJobStatus` 枚举成员，表达
  「未运行即被阻断」而非「运行失败」）。

### 2. `run()` 重写为显式 trio 编排
- 顺序永远由 `TRIO_STEPS` 决定；`payload.steps` 仅做正式子集过滤，**不影响顺序**。
- 建立不可变共享快照：`_build_snapshot_input` → `build_digest` → 写 `job.snapshot_id`；
  三项 item 用 `_stamp_item_contract` 写 `step_key/sequence/snapshot_id`，收尾再
  `DeliverableTrioSnapshot.bind_items_to_snapshot` 把同一 digest 绑到 job + 三项（需求 2.4）。
- 依赖阻断：`audit_report.depends_on=(financial_report, disclosure_notes)`，前置任一未成功
  ⇒ 标 `blocked_by_dependency`、**`continue` 不调用导出器**（design §6：而非伪装成导出异常）。
- 状态聚合**只统计正式三项**：`trio_total=3`、`trio_succeeded=done`；
  `update_progress(done, failed=failed+blocked)` ⇒ 三项成功=succeeded / 部分=partial_failed /
  全失败（含阻断）=failed。
- `_run_financial_reports` 补 fail-closed（`store.version is None → raise`），与
  `_run_disclosure_notes` 同口径（Task 4 已为后者加）。

### 3. 旧 4 步契约测试已按 phase4 权威契约收敛（不是假绿）
`backend/tests/test_full_deliverables_executor.py`：
- `_patch_steps` 的 `fail_step` 改用稳定键（`financial_report/disclosure_notes/audit_report`），
  删去 `financial_reports_unadjusted` 桩（不再是正式步骤），补 `_build_snapshot_input` 桩。
- `test_all_steps_succeed`：断言 done==3 / trio 3/3 / outcomes 顺序==权威三件套 / sequence==[1,2,3]。
- `test_single_step_failure_isolated`：附注失败 ⇒ audit 标 blocked_by_dependency、financial 仍成功。
- `test_first_step_failure_blocks_dependent`（原 `_does_not_abort` 更名）：财报失败 ⇒ 附注仍跑、audit 阻断。
- 新增 `test_all_fail_is_failed_status`：前两项失败 ⇒ audit 阻断 ⇒ 三项无一成功 → failed。
- `test_progress_increments_per_item`：progress_total==3 / trio_total==3。

## 二、新增 Task 5 变异证明测试
`backend/tests/test_phase4_trio_executor_order.py`（SQLite 真 ORM + 真 ExportJob/ExportJobItem）：

正面：
- `test_trio_steps_fixed_order_and_keys` / `test_run_persists_step_key_and_sequence_in_order`
  （真 item 行记录稳定键 + 顺序；辅助项不进正式 item）。
- `test_three_items_share_one_snapshot`（三项 item 的 `snapshot_id` 同一且非空）；
  `test_digest_idempotent_and_binds_source`（同输入 digest 稳定、改输入 digest 变化）。
- `test_audit_blocked_when_prereq_failed_and_no_exporter_run`（附注失败 ⇒ audit=blocked，
  **导出器调用计数==0**，trio_succeeded==1）；`test_blocked_not_counted_as_success`。

变异（改回旧行为必须红 —— 以 monkeypatch 替换 `TRIO_STEPS` 制造旧行为，断言正面不变量被打破）：
- `M1` 调换顺序（audit 先行）⇒ outcomes 顺序 != 权威顺序（顺序断言被打破）。
- `M2` 把 `financial_report_unadjusted` 混入 TRIO_STEPS（算正式项）⇒ outcomes 变 4 项
  （「正式固定 3」判据被打破）。
- `M3` 去掉 `audit_report.depends_on` ⇒ 前置失败后正文照跑（导出器计数==1、audit 不再 blocked），
  证明「依赖阻断」判据可被打破。

## 三、运行证据（Windows / `..\.venv\Scripts\python.exe`）

```
# RED-3 修复前红 → 修复后绿
tests/test_phase4_trio_baseline_red.py::TestTrioStepsAuthoritativeContract
  修复前：2 failed（AssertionError: 缺权威 TRIO_STEPS 常量）
  修复后：2 passed

# Task 5 新测 + 收敛后的 executor 测
tests/test_phase4_trio_executor_order.py + tests/test_full_deliverables_executor.py
  21 passed（含 3 条变异证明 M1/M2/M3）

# 回归（executor 的生产调用方 + 交付中心）
tests/test_phase13_word_export.py + test_deliverable_center_integration.py
  + test_deliverable_center_p0.py = 92 passed / 1 skipped
```

## 四、仍为预期红（非本任务范围，归因）
- `test_phase4_trio_baseline_red.py` RED-2 两条（`test_retry_must_create_attempt_and_regenerate` /
  `test_retry_preserves_original_failure_reason`）：属 **Task 7/8**（`retry_failed` 真正新增 attempt、
  保留失败原因）。本任务未触碰 `retry_failed`。
- `test_service_call_wiring_integrity.py::test_no_call_to_nonexistent_module_or_class_attribute`：
  失败项全在 `wp_guidance_chat.py`（`guidance_inventory` / `guidance_source_refs`），与 phase4 无关。
  **已用 `git stash` 回滚本任务改动复跑 → 同样红**，确认是 **HEAD 预存红**，非本任务引入。

## 五、边界
- 未触碰 `retry_failed`（Task 8）、readiness/生成/重试/下载端点与权限（Task 9）、
  savepoint `begin_nested`（Task 6）。
- 共享键单一真源：`deliverable_trio_snapshot.TRIO_STEP_KEYS`（Task 3）→ executor 导入并断言一致，
  未新建第三份分叉定义。
- `git stash pop`（用于预存红归因）意外在 `.kiro/steering/memory.md` 触发并发会话遗留冲突，
  已保留当前工作树（公式推送阶段节）内容、删去过期的 branch-switch 便签解决，无内容丢失。
