# T10 — ProjectWorkbookInstance 交付与 SYNC gate 状态（2026-09-09）

## 已交付
- `workbook_instance.py`：一 xlsx → 一 instance + N child；统一 `pwi-{wid}:{sheetUid}` entry
- `namespace_migration.py`：legacy opaque 分裂探测 + migration plan（不执行擅自合并）
- `V158__project_workbook_instance.sql` + ORM
- 守卫：`test_workbook_instance.py`（8）

## 仍 BLOCKED（不得假绿勾选 Task 10 的「证明唯一」子弹）
- `SYNC-MULTI-RESOLVER`：`multi_resolver_count=4` deferred
- `SYNC-ENTRY-NAMESPACE`：`ENTRY_ID_NAMESPACE_SPLIT_NOTE` wp_code/wp_id 分裂仍在

探测：`probe_namespace_gates()` / `probe_all_sync_gates()`。
