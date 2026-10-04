# Task 8 — 真正重试失败步骤（交付证据）

> spec `chain-closure-phase4-deliverable-center-trio`，需求 5.2–5.5。
> 分支 `work/2026-10-01-i-cycle-classification-convergence`，基线 HEAD `19c65589d`。
> append-only。

## 一、改了什么

### 1. `FullDeliverablesExecutor`：抽出共享步骤执行单元 + 真正的 retry 入口
`backend/app/services/full_deliverables_executor.py`：

- **`_execute_step_in_savepoint(...)`**：把「start_attempt（savepoint 外）→ `begin_nested()`
  内 `_dispatch_trio_step` + link task + item=succeeded 投影 → 失败则回滚后在保存点外
  `finish_attempt_failed` + item=failed」提炼为**初次生成与重试共用的唯一执行路径**
  （design §7 第 4 步要求 retry 走同一渲染/落盘/指纹/版本流程）。`run()` 的步骤循环改为
  调用它（`trigger="initial"`），行为与 Task 6 逐字节等价（事务边界不变）。
- **`retry_failed(job_id, *, user_id, requesting_project_id=None)`**（design §7）：
  1. 校验 job 存在、（给定时）属于请求 project；
  2. **快照一致性复核**（需求 5.5）：用**同一** `_build_snapshot_input` 复算 digest，与
     `job.snapshot_id` 比对，不一致 ⇒ 抛 `SnapshotMismatchError`（绝不在旧快照上混用新数据）；
  3. 按固定 `sequence` 顺序（前置先于依赖）处理每个带 `step_key` 的 item：
     - `failed` / `blocked_by_dependency` 且前置已成功 ⇒ 经共享单元 `trigger="retry"` 重跑，
       **新增 attempt**（attempt_no 单调递增，原始失败 attempt 永不覆盖，需求 5.4）；
     - `succeeded` 且文件指纹仍有效 ⇒ **复用既有文件、不重跑导出器**（需求 5.3）；
     - audit_report 前置仍未成功 ⇒ 维持 `blocked_by_dependency`，不运行导出器；
  4. `_recompute_job_after_retry` 按正式三件套重算进度/状态与 trio 完成数（需求 2.6/4.4）。
- **`_succeeded_item_file_still_valid`**：复用统一指纹入口 `verify_file_fingerprint`
  （item 投影缺指纹时回退到最新成功版本），任一校验失败即判失效（需重试）。
- **`_finish_attempt_with_fingerprint`**：成功 attempt 收尾时把最新成功版本的
  `version_id/file_path/size/sha256` 写入 attempt（指纹来自 `render_and_store` 已校验落盘的
  最终文件，需求 3.2/5.5，不另算一套）。
- **`SnapshotMismatchError`**：携带两侧 digest，供 router 映射 409。
- **`RetryOutcome`** dataclass：`retried` / `reused` / `outcomes` / `snapshot_id`。
- `StepOutcome` 补 `resolved_opt` / `reused_existing` 字段。

### 2. `ExportJobService.retry_failed`：从「只复位状态」改为真正重试编排
`backend/app/services/export_job_service.py`：

旧实现是 fail-open：只把 item 改回 `queued`、清空 `error_message`、不建 attempt、不重跑、
**洗掉原始失败原因**。新实现：

1. **保留原始失败原因**（需求 5.4）：失败项若尚无 attempt（经 `update_item_status` 直接置失败
   的历史数据/baseline 口径），先按原始 `error_message` **补记**一条已终结失败 attempt
   （`_ensure_original_failure_attempt`，append-only），使重试后历史仍能查到原始原因；
2. **正式三件套 item**（有 `step_key` 且 job 绑定快照）⇒ 懒加载 `FullDeliverablesExecutor`
   委托 `retry_failed` 真正重跑（避免 import 环）；
3. **非三件套 item**（无 `step_key`，旧 `full_package`/批量渲染明细，无专用步骤入口）⇒
   新增一条 retry attempt + 复位 `queued`，原始失败原因已在第 1 步保留。

返回「本次识别并处理的失败项数」。service 只 flush，router 统一 commit。

### 3. 路由最小接线（完整权限属 Task 9）
`backend/app/routers/word_export.py` 的 `POST /jobs/{job_id}/retry`：传 `user_id` /
`requesting_project_id`，并把 `SnapshotMismatchError` 映射为 **409**（需求 5.5）。
> 完整 readiness/创建/重试/下载端点与项目级编辑权限依赖链属 **Task 9**。

## 二、测试与变异证明
新测试文件：`backend/tests/test_phase4_trio_retry_reexecute.py`（SQLite 真 ORM，6 用例全绿）。

- **R1 故障恢复后重试**（需求 5.2/5.4/5.5）：disclosure_notes 初次失败 → audit_report 依赖阻断
  → 恢复后 `executor.retry_failed` → disclosure_notes 重试**产出真实版本行**（`Path.is_file()`
  为真）、audit_report 前置恢复后一并重跑成功；attempt 历史为 `[1=initial/failed, 2=retry/
  succeeded]`，`attempt_no` 单调、**原始失败原因保留**；job `trio_succeeded==3`、状态 succeeded。
- **R2 已成功项复用、不重跑**（需求 5.3）：retry 时 financial_report 导出器调用计数**不增加**，
  其既有真实文件经指纹校验复用，不产生新版本行。
- **R3 快照不一致 ⇒ 409 语义**（需求 5.5）：复算 digest 变化 ⇒ `SnapshotMismatchError`
  （两侧 digest 不等），disclosure_notes 不被重跑、**不新增 retry attempt**。
  另 `test_wrong_project_rejected`：job 不属请求 project ⇒ `ValueError`（Task 9 映射 403）。
- **R4 非三件套 item**（baseline RED-2 口径）：无 `step_key` 的 item retry 仍**新增 attempt**
  且**保留原始失败原因**。
- **M1 变异（测试内）**：把 `retry_failed` monkeypatch 回「只复位 queued」旧实现 ⇒
  retry 后 attempt 数不增（证明判据非恒绿）。

### 变异证明（生产代码实改 → 对应用例变红 → 复原转绿）
把 `ExportJobService.retry_failed` 函数体临时替换为旧 fail-open（只复位 `queued`、清空
`error_message`、不建 attempt、不重跑）后复跑：

```
tests/test_phase4_trio_baseline_red.py::TestRetryActuallyReExecutes
  test_retry_must_create_attempt_and_regenerate      FAILED
    AssertionError: retry 应为失败项新增 attempt，但 attempt 表为空 ⇒ retry 只复位了状态
  test_retry_preserves_original_failure_reason        FAILED
    AssertionError: retry 后原始失败原因应保留在 attempt 历史中，但未找到
tests/test_phase4_trio_retry_reexecute.py::...::test_generic_item_retry_appends_attempt_and_keeps_reason
    FAILED  AssertionError: retry 后原始失败原因须保留在 attempt 历史
→ 3 failed
```
复原生产代码后三条重新全绿。

### 运行证据（Windows / `..\.venv\Scripts\python.exe`，cwd=backend）
```
# Task 8 新测
tests/test_phase4_trio_retry_reexecute.py                       6 passed

# baseline RED-2 两条（本任务目标）由红转绿
tests/test_phase4_trio_baseline_red.py::TestRetryActuallyReExecutes   2 passed

# phase4 定向回归（Task 1/3/5/6/7 + 本任务）
tests/test_phase4_trio_retry_reexecute.py + _baseline_red + _attempt_history
  + _savepoint_isolation + _executor_order + _snapshot_schema
  46 passed

# executor 生产调用方（交付中心 + word export + executor 契约）
tests/test_deliverable_center_integration.py + test_deliverable_center_p0.py
  + test_phase13_word_export.py + test_full_deliverables_executor.py
  104 passed / 1 skipped
```

## 三、边界
- 只做 service/executor 层**真正重试**：共享步骤执行单元、retry 新增 attempt、保留原始失败、
  已成功项复用指纹校验、快照不一致 fail-closed。
- 路由仅最小接线（传 user/project + 409 映射）；完整 readiness/创建/重试/下载端点与项目级
  编辑权限依赖链属 **Task 9**（含 403 零写入、下载前物理哈希校验）。
- 前端失败项重试入口与历史属 **Task 11**。
- service 只 flush 不 commit 的既有铁律保持；commit 仍由 router/编排边界统一执行。
- 真 PG 临时 schema 全链回归（readiness→生成→失败→retry→完成）属 **Task 12/13**。
