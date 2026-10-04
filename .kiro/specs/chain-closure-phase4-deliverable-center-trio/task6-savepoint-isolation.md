# Task 6 — savepoint 隔离与事务边界（交付证据）

> spec `chain-closure-phase4-deliverable-center-trio`，需求 4.1, 4.2, 4.3, 4.5, 7.2。
> 分支 `work/2026-10-01-i-cycle-classification-convergence`，基线 HEAD `19c65589d`。
> append-only。

## 一、改了什么

### 1. executor：每步骤业务写入进 `begin_nested()` 保存点
`backend/app/services/full_deliverables_executor.py` 的 `run()` 步骤循环：

- `add_item` + `_stamp_item_contract` + `start_attempt` 在保存点**之外**执行
  （item 行与 attempt 失败留痕必须在步骤失败时存活，故不进保存点）。
- 步骤的**业务写入**（`_dispatch_trio_step` → 版本/task 状态/章节状态、`_link_item_task`、
  item=succeeded 投影）包进 `async with self.db.begin_nested()`：
  - 成功 ⇒ 保存点随上下文退出自动 RELEASE，业务写入与「item=succeeded」一起留在外层事务
    （由 router 统一 commit）。
  - 失败 ⇒ 保存点 ROLLBACK，撤销本步骤半成品业务写入（例如第 2 步已 flush 的临时版本行
    不残留）；回滚**之后**在保存点外记 `finish_attempt_failed` + item=failed —— 两条失败
    留痕因在保存点外故不被回滚（需求 4.2）。
  - 已成功步骤的 item/版本在其保存点 RELEASE 后已属外层事务，不被后续步骤保存点回滚波及
    （需求 4.2「其他已成功步骤不得被回滚」）。
- 依赖阻断（`blocked_by_dependency`）从未运行导出器，**不开 attempt、不进保存点**。
- service 仍只 `flush` 不 `commit`；commit 由 router/编排边界统一执行（需求 4.1）。

### 2. `ExportJobService` 新增 attempt append-only 管理（design §3.3）
`backend/app/services/export_job_service.py`：

- `start_attempt(job_id, item_id, *, snapshot_id, trigger, created_by)`：
  `attempt_no` = 该 item 现有最大值 +1（单调递增）；同时更新 item 的 `attempt_count` /
  `last_attempt_id` 投影。**必须在保存点外调用**（见 docstring）。
- `finish_attempt_success(attempt_id, *, version_id, file_path, file_size, file_sha256)`。
- `finish_attempt_failed(attempt_id, exc, *, user_message, diagnostic_detail)`：
  保存 `error_type`（异常类名）、中文 `error_message`、`diagnostic_detail`（含 step/sequence）；
  append-only 永不覆盖。**必须在保存点回滚之后调用**。

> 范围克制：**未**触碰 `retry_failed`（Task 8）、路由端点/权限（Task 9）。attempt 的
> `trigger="initial"` 由本任务写；retry 触发的 attempt 属 Task 8。

## 二、测试与变异证明
新测试文件：`backend/tests/test_phase4_trio_savepoint_isolation.py`。

### A 组 SQLite 真 ORM（aiosqlite 支持 SAVEPOINT）
桩：第 1 步落**真实成功版本行**；第 2 步**先 flush 一个半成品版本行、再抛 `ValueError`**
（模拟「版本先写、随后指纹校验失败」）；第 3 步依赖前两项。

- `test_step2_partial_rolled_back_step1_survives_failure_logged`：
  第 1 步版本存活 + item=succeeded；第 2 步半成品版本**被回滚**（不残留）+ item=failed；
  第 3 步 `blocked_by_dependency`；第 2 步失败 attempt **存活**（保存点外记录）；
  `trio_succeeded==1 / trio_total==3`。
- `test_failed_attempt_records_error_type_message_and_stage`（需求 4.3）：
  失败 attempt 的 `error_type=="ValueError"`、中文消息含「附注/校验」、
  `diagnostic_detail["step"]=="disclosure_notes"`、`attempt_no==1`、`finished_at` 非空。
- `test_mutation_remove_savepoint_leaks_partial_write`（变异）：
  把 `executor.db.begin_nested` 替换成**不隔离的空上下文** ⇒ 第 2 步半成品版本泄漏存活
  （断言存活=True），证明保存点判据非恒绿；同时断言失败 attempt 仍存活（证明「失败留痕
  在保存点外」与「业务写入在保存点内」是两条独立边界）。

### B 组 真 PG16（无 PG 环境自动 skip；本机 `audit-postgres` 可连）
- `test_pg_native_savepoint_isolates_step2_and_keeps_failure_trace`：
  在真 PG 一次性库上以**原生 SAVEPOINT** 跑同一 executor 流程 + 外层 `commit`，
  落库后复查：第 1 步版本存活、第 2 步半成品**被 `ROLLBACK TO SAVEPOINT` 回滚**、
  失败 attempt 随外层 commit 落库存活。
  - 临时库建表用裸 DDL（只建 executor 实际触碰的 7 张表，去 FK），避开
    `Base.metadata.create_all` 的全量 FK 闭包与未安装的 `vector` 扩展（本机 PG 无 pgvector）。

### 运行证据（Windows / `..\.venv\Scripts\python.exe`，cwd=backend）
```
# Task 6 新测（含真 PG）
tests/test_phase4_trio_savepoint_isolation.py
  4 passed（3 SQLite + 1 真 PG16）

# 「去掉 savepoint 必须红」—— 生产代码临时移除 begin_nested（if True 直跑）复跑：
  test_step2_partial_rolled_back_...（SQLite）+ test_pg_native_savepoint_...（真 PG）
  2 failed，断言精确命中「半成品版本必须随保存点回滚（需求 4.2）」
  复原生产代码后两条重新 4 passed。

# 回归（Task 3/5 + executor 契约 + baseline-red）
tests/test_phase4_trio_executor_order.py + test_phase4_trio_snapshot_schema.py
  + test_full_deliverables_executor.py + test_phase4_trio_baseline_red.py
  40 passed / 2 failed

# executor 生产调用方（交付中心 + word export）
tests/test_deliverable_center_integration.py + test_deliverable_center_p0.py
  + test_phase13_word_export.py = 92 passed / 1 skipped
```

## 三、仍为预期红（非本任务范围，归因）
- `test_phase4_trio_baseline_red.py::TestRetryActuallyReExecutes` 两条
  （`test_retry_must_create_attempt_and_regenerate` / `test_retry_preserves_original_failure_reason`）：
  属 **Task 7/8**（`retry_failed` 真正新增 attempt、保留原始失败原因）。本任务**未**触碰
  `retry_failed`。已用 `git stash push` 回滚本任务对 `full_deliverables_executor.py` /
  `export_job_service.py` 的改动后在 HEAD 复跑 → **同样 2 failed**，确认是 **HEAD 预存红**，
  非本任务引入；`git stash pop` 已复原工作树（无内容丢失）。

## 四、边界
- 只做步骤级 savepoint 隔离、事务边界与 attempt append-only 写入（initial 触发）。
- 未触碰 `retry_failed`（Task 8）、readiness/生成/重试/下载端点与权限（Task 9）。
- service 只 flush 不 commit 的既有铁律保持；commit 仍由 router/编排边界统一执行。
- 真 PG 临时库用完即删（`DROP DATABASE`），不写真实项目库作本任务通过证据（需求 7.5）。
