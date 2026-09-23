# Suite triage: task27 conflict-resolution + task28 sync-router (PG)

状态：进行中（stub 先落盘，findings 随得随 append）

## 范围
- `backend/tests/workpaper_sync/test_task27_conflict_resolution_pg.py`
- `backend/tests/workpaper_sync/test_task28_sync_router_pg.py`
- 非 PG 兄弟 `backend/tests/workpaper_sync/test_task28_sync_router.py`（如成本低）

## 关键怀疑点（本会话改动）
本会话两次改 `backend/app/routers/wp_sync_router.py`：
1. task 10：`materialize` 端点加 2 个 metrics emit（`REUSE_METRIC` / `SINGLE_PASS_DECLINE_METRIC`）+ `single_pass_decline_scope()` 包裹 `coordinator.materialize(...)` + defect-class ERROR 日志
2. task 11：新增端点 `POST …/rooms/{room_id}/participants/{participant_id}/leave`（`leave_room`）

需判定：失败是"我们的回归"还是"预存"。Task 3 早前 A/B 差分把此簇标为预存，但那次 A/B 跑在 task 10/11 之前，不覆盖。

## 附加核查
`leave_room` 是否真的注册进 `backend/app/router_registry/`（定义但未注册 = 404 且测试无感知）。

---

## 运行记录（append）

### task28_sync_router_pg BEFORE
命令（cwd=backend）：
`rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task28_sync_router_pg.py -q --tb=short -rf -p no:randomly`
结果：**8 failed, 39 passed**（10.90s）

失败 8 例按根因分组 —— **只有 1 个根因**：
```
ProgrammingError UndefinedTableError: relation "wp_index" does not exist
[SQL: SELECT s.current_representation_id AS rid
      FROM working_paper_sync_entry_state s
      JOIN working_paper wp ON wp.id = s.wp_id
      JOIN wp_index wi ON wi.id = wp.wp_index_id
      JOIN projects p ON p.id = wp.project_id
      WHERE s.entry_id = $1 ... ORDER BY wp.created_at, wp.id LIMIT 1]
[parameters: ('xlsx/gt-d2-accounts-receivable',)]
```
- 抛出点：`backend/app/services/workpaper_sync/projection_target_resolution.py:275`
  `resolve_visible_current_representation_id()`（BP-27 收敛出的**唯一**可见性口径）
- 调用链：router `_materialize_request` → `_registration` → `_attach_pilot_adapters`
  → `pilot_d2_large_json.attach_pilot_adapters`（其 `PILOT_ENTRY_ID` 正是测试 fixture 的
  `ENTRY = "xlsx/gt-d2-accounts-receivable"`）
- 2 个 harness 阶段崩（`pending_mutation` / `rollback`）→ 快照缺 2 个 scenario key →
  2 个 TestHarnessIntegrity + 2 个 TestFlushDoesNotAdvanceRevision + 4 个
  TestOpaqueVersionIdRollback 共 **8 例**全是这一个根因的下游。

### ours vs pre-existing 判定：**pre-existing（不是本会话回归）**
证据：
1. 失败与 route 表/metrics 集合/端点清单**无关**——错误是 PG `UndefinedTableError`，
   在 `_registration` 阶段就抛了，还没走到 task 10 的 metrics 或 task 11 的 leave_room。
2. 崩溃链上的文件**全部工作树未修改**（`git status --porcelain` 无这些条目）：
   `pilot_d2_large_json.py` / `projection_target_resolution.py` / `entry_profile.py` /
   `backend/data/workpaper_sync_entry_manifest.json`。
3. 触发条件是 manifest 的 D2 entry capability 已翻成 `bidirectional`
   （实测 `manifest_capability_enabled() == True`），使 pilot 的
   「capability 未启用就 return () 且一次库都不读」早退路径**不再生效** →
   首次真的去读库。该 manifest 最后一次改动在 **已提交** 的 `0c9eb40d6`
   （`git log -- backend/data/workpaper_sync_entry_manifest.json`），工作树 clean。
4. 本会话 `wp_sync_router.py` 的 3 个 hunk 分别落在 `materialize`(~870)、
   新 `leave_room`(~1491)、`_build_error_code_status`(~2966)，均不在
   `pending-mutations` / `versions/{id}/rollback` 路径，且没有任何 `wp_index` 查询新增
   （`git diff | Select-String wp_index` 为空）。

→ 结论：Task 3 早前 A/B 把此簇标 pre-existing 是**对的**，即使 A/B 跑在 task 10/11 之前，
本次独立复核（根因 + 工作树 diff 双重证据）仍得出同一结论。

