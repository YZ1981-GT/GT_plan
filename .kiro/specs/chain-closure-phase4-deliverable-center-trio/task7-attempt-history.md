# Task 7 — job/item/attempt 不可变历史 + fail-closed 恢复（交付证据）

> spec `chain-closure-phase4-deliverable-center-trio`，需求 4.3, 4.4, 4.6, 5.4。
> 分支 `work/2026-10-01-i-cycle-classification-convergence`，基线 HEAD `19c65589d`。
> append-only。

## 一、改了什么

### 1. `ExportJobService`：attempt append-only 守护 + 历史查询 + fail-closed 恢复
`backend/app/services/export_job_service.py`：

- 新增 `ImmutableAttemptError` 与 `_ATTEMPT_TERMINAL_STATUSES = {succeeded, failed}`。
- `_assert_attempt_mutable(attempt)`：若 attempt 已处于终态则抛 `ImmutableAttemptError`。
  在 `finish_attempt_success` / `finish_attempt_failed` 入口调用 —— **对已终结 attempt 的二次
  finish/改写一律拒绝**，杜绝「把多次尝试压成一个时间点」或「洗掉原始失败原因」（需求 4.3/5.4）。
- `get_item_attempts(item_id)` / `get_job_attempts(job_id)`：返回**完整** append-only 历史，
  按 `attempt_no` 升序（job 级按 `(item_id, attempt_no)` 稳定排序）。前端刷新 job 据此拿到
  原始失败 attempt + 后续重试 attempt，不得用空数组覆盖（design §7 末段）。
- `recover_orphaned_running(job_id)`：**fail-closed 恢复**（需求 4.6）。扫描因进程中断/超时
  遗留在 `running` 的 attempt，一律标 `failed` + `error_type='Interrupted'` + 中文诊断 +
  `diagnostic_detail["recovered_from_running"]=True`，**保留原 attempt_no 与开始时间**（不新增、
  不改写已终结项）；对应 item 若仍 `running`/`queued` 也 fail-closed 标 `failed`。
  **决不执行 `running → succeeded`**。service 只 flush，由 router/编排统一 commit。

> 范围克制：**未**触碰 `retry_failed`（Task 8）。本任务只做历史不可变性、恢复 fail-closed 与
> 历史查询（含只读 HTTP 端点）。

### 2. 响应 schema
`backend/app/models/phase13_schemas.py` 新增 `ExportJobAttemptResponse`：完整承载
`attempt_no / status / trigger / snapshot_id / error_type / error_message /
diagnostic_detail / file_* / version_id / started_at / finished_at`。

### 3. 只读 HTTP 端点（TestClient 查询）
`backend/app/routers/word_export.py` 新增
`GET /api/projects/{project_id}/word-exports/jobs/{job_id}/attempts`：
返回整个 job 的 append-only 尝试历史；校验 job 属主项目（错项目 403）。

**HTTP 边界说明**：正式交付中心路由（`/deliverables/jobs/{job_id}` 等）由 **Task 9** 建立并
在 router_registry 新增注册。本只读端点挂在**既有**、已由 `router_registry/report.py` 注册的
`word-exports` 路由下，满足 Task 7「TestClient 查询完整历史」验收，**不新增 router 注册**。

## 二、测试与变异证明
新测试文件：`backend/tests/test_phase4_trio_attempt_history.py`（SQLite 真 ORM + TestClient）。

### 覆盖（10 用例全绿）
- **失败记录字段完整**（需求 4.3）：`error_type=="ValueError"` + 中文消息 + `diagnostic_detail`
  含 step/sequence（阶段）+ `snapshot_id` + `finished_at` + `attempt_no`。
- **单调编号 + 保留原因**（需求 5.4）：两次尝试 `attempt_no == [1, 2]`，原始失败原因保留在历史；
  item 投影 `attempt_count==2`、`last_attempt_id` 指向最新；唯一索引拒绝手工撞号 `attempt_no`。
- **append-only 守护**：对已终结 attempt 的二次 `finish_attempt_success` / `finish_attempt_failed`
  抛 `ImmutableAttemptError`，原始原因/状态不被污染。
- **恢复 fail-closed**（需求 4.6）：遗留 running 的 attempt+item 恢复为 `failed`（含 `Interrupted`
  + `recovered_from_running`，attempt_no 不变）；已终结 attempt 不被波及。
- **TestClient 查询**：`GET .../jobs/{job_id}/attempts` 返回**完整** 2 条历史（含第一次失败原因、
  trigger、诊断），错项目 403。

### 变异证明（生产代码临时改坏 → 对应正确性用例变红 → 复原转绿）
1. **覆盖写旧 attempt 必红**：把 `_assert_attempt_mutable` 的终态判断短路成 `if False and ...`
   ⇒ `test_cannot_overwrite_finished_failed_attempt` 变红
   （`Failed: DID NOT RAISE ImmutableAttemptError`）。复原后转绿。
2. **恢复 fail-closed 必红**：把 `recover_orphaned_running` 里 `attempt.status = failed`
   改成 `= succeeded` ⇒ `test_orphaned_running_attempt_and_item_recovered_to_failed` 变红
   （`AssertionError: 'succeeded' == 'failed'`）。复原后转绿。
   （文件内另有两个「变异反证」用例以 monkeypatch 构造错误实现并断言被禁行为确实发生，
   证明判据非恒绿，与上述对生产代码的实改互为印证。）

### 运行证据（Windows / `..\.venv\Scripts\python.exe`，cwd=backend）
```
# Task 7 新测
tests/test_phase4_trio_attempt_history.py        10 passed

# 变异（生产代码实改）
_assert_attempt_mutable 短路      → test_cannot_overwrite_finished_failed_attempt 1 failed
recover 改 succeeded             → test_orphaned_running..._recovered_to_failed  1 failed
复原生产代码后两条重新全绿。

# phase4 定向回归（Task 3/5/6 + baseline-red）
tests/test_phase4_trio_attempt_history.py + _savepoint_isolation + _executor_order
  + _snapshot_schema + _baseline_red
  38 passed / 2 failed

# 生产调用方回归（word export + 交付中心）
tests/test_phase13_word_export.py + test_deliverable_center_integration.py
  + test_deliverable_center_p0.py = 92 passed / 1 skipped
```

## 三、仍为预期红（非本任务范围，归因）
- `test_phase4_trio_baseline_red.py::TestRetryActuallyReExecutes` 两条
  （`test_retry_must_create_attempt_and_regenerate` / `test_retry_preserves_original_failure_reason`）：
  属 **Task 8**（`retry_failed` 真正新增 attempt、重跑步骤、保留原始失败原因）。Task 6 交付文档
  已记录其为 HEAD 预存红。本任务**未**触碰 `retry_failed`，故这两条维持预存红状态，与本任务
  引入无关。本任务已为 Task 8 铺好地基：`start_attempt`（单调编号）、历史查询、append-only 守护
  与恢复 helper 均就位，Task 8 的 retry 只需「新增 attempt + 调步骤入口」即可让这两条转绿。

## 四、边界
- 只做 attempt append-only 不可变性、历史查询（service + 只读 HTTP 端点）与中断/超时 fail-closed
  恢复。未触碰 `retry_failed`（Task 8）、readiness/生成/重试写端点与权限（Task 9）。
- service 只 flush 不 commit 的既有铁律保持；只读历史端点不写库、不 commit。
- 未新增 router 注册：历史端点挂在既有已注册的 `word-exports` 路由下。
