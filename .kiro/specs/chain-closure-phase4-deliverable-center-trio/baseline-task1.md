# Task 1 基线与入口清册（red-before 证据）

> spec: `chain-closure-phase4-deliverable-center-trio` / 任务 1。
> 本文件是现状审计 + 修复前红基线，供后续任务对照。append-only。

## 一、git / HEAD / 工作树状态

- 当前分支：`work/2026-10-01-i-cycle-classification-convergence`
- HEAD：`19c65589d`（与 `origin/...` 同步）
- 工作树（`git status --short`）：
  - ` M .kiro/specs/chain-closure-phase4-deliverable-center-trio/tasks.md`（本 spec 任务状态，并行/本任务编辑）
  - ` M audit-platform/frontend/src/auto-imports.d.ts`（并行自动生成，**不覆盖**）
  - `?? .agents/tasks/checksum-drift-8/*`、`?? .../tasks.meta.json`（并行/工具产物）
- 结论：**无合并冲突、无 phase2/phase3 未跟踪生产模块遗留**。交付相关生产文件（executor / service / router / model / frontend）工作树 == HEAD，逐块审计未发现并行改动，可安全在其上编辑。

## 二、现算：三个核心对象的当前行为

### 2.1 `FullDeliverablesExecutor`（`backend/app/services/full_deliverables_executor.py`）

- 权威步骤常量只有 `FULL_DELIVERABLES_STEPS = ["financial_reports", "disclosure_notes", "report_body"]`。
  - 🔴 用**非权威键**：`financial_reports`（spec 要 `financial_report`）、`report_body`（spec 要 `audit_report`）。
  - 🔴 **无 `TRIO_STEPS` 常量**，顺序/稳定键没有权威来源；dispatch 用 `if step == ...` 字符串分支。
  - `financial_reports_unadjusted` 有独立分支实现，但默认 steps 过滤 `[s for s in FULL_DELIVERABLES_STEPS if s in steps]` 会把它丢弃 ⇒ 默认不计入，但也没有被**显式**标为辅助/排除。
- `run()`：每步 `try/except` 捕获后 `continue`（单项失败隔离），用 `done/failed` 计数 + `update_progress` 落 `partial_failed`。**无 savepoint（`begin_nested`）**，无 attempt 记录，无共享 snapshot_id 绑定，audit 对 disclosure 失败无 `blocked_by_dependency` 概念。

### 2.2 `ExportJobService.retry_failed`（`backend/app/services/export_job_service.py:182`）

- 当前实现：查 `status=failed` 的 item → 逐个 `item.status = queued; item.error_message = None; item.finished_at = None` → job 状态改 `running`、`failed_count=0`、`progress_done -= retried`。
- 🔴 **只复位状态**：不调用任何渲染/落盘/指纹/版本函数，不新增 attempt，**清空** `error_message`（原始失败原因丢失）。

### 2.3 `DeliverableService.render_and_store`（`backend/app/services/deliverable_service.py:414`）

- 落盘 `try/except`：写盘失败时 `platform_persist_failed=True; file_path=None`，**随后仍无条件调用 `create_version(file_path=None, ...)`**。
- 🔴 **fail-open**：写盘失败照样产生版本行（`file_path IS NULL`）。只有 hash 绑定（`DeliverableHashService.bind_version_hash`）与 task 字段更新被 `platform_persist_failed` 跳过。
- 无"生成→落盘→校验（is_file / 可读 / size>0 / SHA-256）→再建版本"的 fail-closed 分段；`verify_file_fingerprint` / `compute_file_fingerprint` 统一入口不存在。

## 三、现有契约（路由 / 模型 / 迁移 / 前端）

- 路由（`backend/app/routers/word_export.py`）：
  - `POST /full-deliverables` → `executor.run` + router commit（已符合"service flush / router commit"）。
  - `POST /jobs/{job_id}/retry` → 只校验 `job.project_id == project_id`，鉴权仅 `get_current_user`（登录即可，🔴 无项目编辑/交付角色门控）；body 调 `retry_failed`。
  - `GET /{task_id}/download` → 仅 `task.file_path` 存在 + `Path.exists()`，🔴 **无 size/SHA-256 指纹校验**，鉴权仅登录。
- 模型（`backend/app/models/phase13_models.py`）：
  - `WordExportTaskVersion`：有 `file_path / file_size / file_hash(String64) / drift_report / source_snapshot_refs`，🔴 **无 per-version `file_sha256` 命名列**（hash 存 `file_hash`，由 `DeliverableHashService` 旁路绑定），无 `snapshot_id` 直绑。
  - `ExportJob` / `ExportJobItem` 存在；🔴 **无 `ExportJobAttempt` 模型 / 表**（append-only 失败历史缺失）。
  - item 无稳定 `step_key` / `sequence` 列。
- 迁移：`backend/migrations` 最高 **V179**（count=179）。新增 job/item/attempt/snapshot 字段应从 **V180** 起、`IF NOT EXISTS`、数值版本不撞号。
- 前端（`audit-platform/frontend/src/services/deliverableApi.ts`）：
  - `ExportJobItem` 用可选英文字段（`error_message?/finished_at?`），🔴 **无 `TrioStepKey` / `ReadinessResult` / `ExportJobAttempt` 类型**，无 readiness/trio 专用端点封装。

## 四、修复前红用例（指向实际错误形态）

测试文件：`backend/tests/test_phase4_trio_baseline_red.py`（本任务新增，red-before 基线）。

命令：`..\.venv\Scripts\python.exe -m pytest tests/test_phase4_trio_baseline_red.py -q`（cwd=backend）

当前结果：**5 failed**，失败断言均指向实际错误形态：

| 用例 | 实际失败形态（当前 HEAD） |
|---|---|
| `test_write_failure_must_not_create_version` | `AssertionError: 写盘失败后不应创建版本，但发现 2 个版本行：[(1, None), (2, None)]` —— render_and_store fail-open 产生 file_path=None 的版本 |
| `test_retry_must_create_attempt_and_regenerate` | `ImportError: cannot import name 'ExportJobAttempt'` —— 无 attempt 机制，retry 只能复位状态 |
| `test_retry_preserves_original_failure_reason` | 同上 ImportError —— 无 attempt 历史可保留原始失败原因（且现实现清空 error_message） |
| `test_trio_steps_canonical_keys_and_order` | `AssertionError: 应存在权威常量 TRIO_STEPS（当前只有 FULL_DELIVERABLES_STEPS）` |
| `test_unadjusted_not_in_trio` | 同上，缺 TRIO_STEPS 权威契约 |

## 五、预存红归因（非本阶段引入）

`backend/tests/test_full_deliverables_executor.py` 现有 **5 failed**（`test_all_steps_succeed` 等断言 `done==4 / progress_total==4`）。这些断言的是**旧 4 步契约**（含 unadjusted 计入），与当前 3 步实现不符 —— 属 **HEAD 预存红**，与本阶段改动无关。本文件未修改该测试文件。后续若按 phase4 把执行器改为权威 TRIO_STEPS，需在相应任务一并裁定这些旧断言的去留（它们正是"unadjusted 计入三件套"反模式的旧测试样本）。

## 六、下一步（Task 2+ 依赖）

1. Task 2 readiness 硬/软闸门（phase3 未入库能力 fail-closed）。
2. Task 3 V180+ 迁移 + ORM：新增 `ExportJobAttempt` / snapshot / item step_key·sequence / version file_sha256·snapshot_id。
3. Task 4 `render_and_store` fail-closed 分段 + 统一指纹函数（本文件 RED 1 转绿）。
4. Task 5/6 `TRIO_STEPS` 权威常量 + savepoint（RED 3 转绿）。
5. Task 7/8 attempt append-only + 真正重试（RED 2 两条转绿）。
