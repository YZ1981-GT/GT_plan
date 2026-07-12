# Implementation Plan · 项目级底稿批量导入导出（workpaper-bulk-tab-import-export）

## Overview

本任务清单把 `design.md` 的编排层方案转化为可执行编码步骤，严格遵循「复用优先、非破坏、fail-soft、快照可回滚、安全边界在后端」原则。任务按 Phase（P1 D 试点 → P2 扩循环 → P3 异步/审计 → P4 异构评估）组织。

- **Phase 1（D 试点）= 关键路径**，位于 Wave 0–6，必做，覆盖 MVP 4 场景。
- **Phase 2/3/4** 位于 Wave 7+，子任务标 `*`（optional，按平台约定仍需完成，排期靠后）。
- 每条 Correctness Property（P1–P8）都有对应 PBT：后端 hypothesis `@settings(max_examples=100)`，前端 fast-check `{ numRuns: 100 }`。
- 后端服务 `backend/app/services/bulk_tab/`；路由 `backend/app/routers/wp_bulk_router.py`（经 `router_registry` 注册）；前端唯一路径 `audit-platform/frontend/`。

### 工程铁律（贯穿所有任务）

- **只读 ACNR 做路由真源**：manifest 字段只来自 `acnr/manifest.list_import_export`；排序只用 `wp_bulk_tab_export._topological_sort`；Excel 只走单表 I/E 执行层。**不手写 sheet 清单、不新造 xlsx 列格式**。
- **service 只 flush 不 commit**；新增 componentType/端点必查 `router_registry`；中文文件名 RFC5987。
- **Vue 文件仅结构化编辑**（禁 PowerShell Set-Content/-replace，U+FFFD 铁律）；改动后必 Playwright 实测（反假绿）。
- **快照优先**：任何写库路径前先 version-trail 快照；失败可回滚。
- **fail-soft**：单 Tab 失败逐条记报告，不整包失败。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3"] },
    { "id": 3, "tasks": ["4.1", "4.2", "4.3", "4.4"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3"] },
    { "id": 5, "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["8.1", "8.2", "9.1", "10.1", "11.1"] },
    { "id": 8, "tasks": ["12.1"] }
  ]
}
```

## Tasks

### Phase 1 · D 试点（Wave 0–6，关键路径，覆盖 MVP）

- [x] 1. ManifestBuilder（唯一读 ACNR）
  - [x] 1.1 实现 `backend/app/services/bulk_tab/manifest_builder.py`
    - `build_manifest(db, project_id, cycles, mode)`：逐 cycle 调 `wp_bulk_tab_export.list_export_sheets` 汇总 entries → 生成 §8.6.6 字段的 `BulkManifest`（addr_id/wp_code/parent_wp_code/sheet_code/sheet_name/origin/api_prefix/item_id/storage_field/wp_id/import_order/depends_on_sheets/zip_path/sha256）+ 头部 exported_at/exported_by/platform_version/mode/cycles
    - `zip_path` = `{cycle}/{parent_wp_code}/{sheet_code}_{short_label}_{模板|数据}.xlsx`；`short_label` = sheet_name 去 sheet_code 后缀并 slug 化
    - `skip_reason`/`wp_id=None` 条目写入 `skipped[]`，不产 xlsx
    - _Requirements: 1.4, 1.5, 1.6, 1.8, 7.1, 7.2, 7.3_
  - [x] 1.2 ACNR 加载失败降级
    - catalog 不可用时抛明确异常，不静默退回分散 JSON
    - _Requirements: 7.4_

- [x] 2. SingleTabIeAdapter（屏蔽执行层差异，D 循环）
  - [x] 2.1 实现 `backend/app/services/bulk_tab/single_tab_adapter.py`
    - `export_tab(db, wp_id, api_prefix, sheet_code, mode) -> bytes`：直调各循环 `_{cycle}_import_export.py` 的 workbook 构建纯函数（template/data）
    - `import_tab(db, wp_id, api_prefix, sheet_code, xlsx_bytes, strategy) -> TabImportResult`：解析 xlsx → 经 ConflictResolver 写库；返回行数/错误/超限告警
    - `IE_ADAPTER_REGISTRY[api_prefix]` 注册 d1~d7；未注册 → 调用方标 `skip_reason=no_adapter`
    - _Requirements: 1.3, 2.1, 2.7_
  - [x] 2.2 D 循环 adapter 接线（d1~d7）
    - 逐 prefix 映射到既有单表 I/E 底层函数（复用，不重写列格式）
    - _Requirements: 1.3, 2.1_

- [x] 3. ConflictResolver + SnapshotGuard + WorkflowGate
  - [x] 3.1 实现 `ConflictResolver`（`overwrite`/`fill-empty`/`reject`）
    - overwrite=全量替换 item_id 行；fill-empty=仅写空位不覆盖非空；reject=目标非空则该 sheet 不写并抛 ConflictRejected
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [x] 3.2 实现 `SnapshotGuard`（复用 version-trail）
    - `snapshot(db, wp_ids)` 调 version-trail 服务层建 pre-import 快照记 snapshot_id；`rollback(db, snapshots)` 恢复；默认 per-sheet + all-or-nothing 开关
    - _Requirements: 2.4, 6.2_
  - [x] 3.3 实现 `WorkflowGate`
    - `classify(plan)`：review_passed/archived/锁定→blocked；under_review→revert_needed；其余→writable
    - `revert_if_under_review`：有编制权回退编制中+审计日志；无编制权不改状态不写
    - _Requirements: 4.3, 4.4, 9.1, 9.2, 9.3_

- [x] 4. BulkExport_Service + BulkImport_Service
  - [x] 4.1 实现 `bulk_export_service.export(...)`
    - 遍历 manifest.exportable() → export_tab → ZipAssembler.write(zip_path)；mode=data 且 only_with_data 时空表标 skipped(no_data)；写 manifest.json + README.txt（逐 Tab 链编制提示）
    - _Requirements: 1.1, 1.2, 1.7, 3.1, 3.2, 3.3, 6.3_
  - [x] 4.2 实现 `ZipAssembler` / `ZipReader`
    - 组装/解析 ZIP；ZipReader 校验 manifest 完整性、单文件+总大小上限、sha256；中文文件名 RFC5987
    - _Requirements: 1.4, 6.3, 6.5_
  - [x] 4.3 实现 `bulk_import_service.dry_run(...)`
    - 校验 manifest/完整性/表头/工作流状态门禁，不写库，返回逐文件预检报告
    - _Requirements: 2.3_
  - [x] 4.4 实现 `bulk_import_service.run(...)`
    - align(manifest, list_import_sheets) 标 missing/unlisted → WorkflowGate 分类 → SnapshotGuard 快照 → 按拓扑顺序逐 sheet import_tab → 汇总 ImportReport → 审计日志；失败按策略回滚；成功 sheet 由单表 import 内部 WORKPAPER_SAVED 触发联动重算
    - _Requirements: 2.1, 2.2, 2.5, 2.6, 2.7, 2.8, 2.9, 4.1, 4.2_

- [ ] 5. 路由 + 权限门禁
  - [-] 5.1 实现 `backend/app/routers/wp_bulk_router.py` 导出端点
    - `POST /export-templates`、`POST /export-data`（≥只读）；循环多选；返回 ZIP 或 task_id
    - 经 `router_registry` 注册
    - _Requirements: 1.1, 1.2, 3.1, 5.1, 5.2_
  - [-] 5.2 实现导入 + 回滚端点
    - `POST /import`（multipart ZIP，dryRun?、strategy；`require_wp_edit_permission`）；`POST /import/rollback`（项目经理）；只读/锁定项目拒绝导入
    - _Requirements: 2.3, 5.3, 5.4, 5.5_
  - [-] 5.3 SSE 进度端点
    - `GET /progress/{task_id}`（复用现有 SSE 模式）
    - _Requirements: 6.1_

- [ ] 6. 前端三按钮 + 导入报告
  - [-] 6.1 实现 `WpBulkDialog.vue`
    - 三按钮（导出全部模板/导入全部数据/导出全部数据）+ 循环多选 + 冲突策略 radio + only_with_data 勾选 + DryRun 开关；与 `WpBatchExportDialog` 并列
    - _Requirements: 5.1_
  - [~] 6.2 实现 `WpBulkImportReport.vue`
    - 逐 sheet 表格（success/partial/failed/missing/unlisted/blocked_by_status/conflict_rejected + 行数 + 错误）；DryRun 与正式共用
    - _Requirements: 2.5, 8.4_
  - [~] 6.3 接入 SSE 进度条（复用现有组件）
    - _Requirements: 6.1_
  - [-] 6.4 导入导出 API composable
    - `useBulkTabImportExport.ts`：走 http(axios) 带 Authorization；ZIP 下载/上传（multipart）
    - _Requirements: 5.1, 5.2, 5.3_
  - [ ]* 6.5 前端 vitest（组件挂载 + 报告状态渲染）
    - _Requirements: 5.1, 2.5_
  - [~] 6.6 Playwright D 循环往返实测（MVP 场景 1/2/3）
    - admin/admin123 → 导出 D 模板 ZIP → 填 3 张代表表 → 导入 → 数据一致 + D2-1↔D2-2 SUMIF 联动 + 回滚一致；0 console error
    - _Requirements: 2.1, 2.2, 4.1_

- [ ] 7. Checkpoint · Phase 1（D 试点）+ PBT
  - Ensure all tests pass, ask the user if questions arise. 确认 MVP 4 场景通过、PBT P1–P8 全绿。
  - [ ]* 7.1 编写 Correctness Property PBT（P1–P8）
    - **P1 拓扑顺序满足依赖**（Validates: 2.2；复用 `test_bulk_topological_sort_pbt.py`，断言编排层不改变性质）
    - **P2 manifest 路由仅来自 ACNR**（Validates: 7.1, 7.2）
    - **P3 跳过项不影响其余**（Validates: 1.6, 1.8, 2.7, 2.8, 2.9）
    - **P4 ConflictStrategy 语义正确**（Validates: 8.1, 8.2, 8.3）
    - **P5 DryRun 不写库**（Validates: 2.3）
    - **P6 失败回滚恢复导入前状态**（Validates: 2.4, 6.2）
    - **P7 工作流状态门禁**（Validates: 9.1, 9.2, 9.3, 4.3, 4.4）
    - **P8 ZIP 不含敏感信息且路径规范**（Validates: 6.3, 1.4）
    - 后端 hypothesis `@settings(max_examples=100)`；前端 fast-check `{ numRuns: 100 }`；注释 `Feature: workpaper-bulk-tab-import-export, Property {n}`

### Phase 2 · 扩循环（Wave 7，optional `*`，排期靠后）

- [ ] 8. adapter 注册表扩 K/F/G/H
  - [ ]* 8.1 扩 `IE_ADAPTER_REGISTRY` 到 K/F/G/H（ACNR manifest 已覆盖）
    - _Requirements: 7.1_
  - [ ]* 8.2 逐循环 Playwright 往返回归
    - _Requirements: 2.1, 2.2_

### Phase 3 · 异步/审计强化（Wave 7，optional `*`）

- [ ] 9. 异步任务 + 审计看板
  - [ ]* 9.1 大项目异步导出/导入（复用 batch-export-async）+ all-or-nothing 开关 + 审计日志汇总
    - _Requirements: 6.1, 6.2, 4.2_

### Phase 4 · 契约守卫 + 异构评估（Wave 7–8，optional `*`）

- [ ] 10. manifest 契约 CI 守卫
  - [ ]* 10.1 CI drift guard：校验 manifest 字段 100% 来自 ACNR catalog
    - _Requirements: 7.1, 7.2_

- [ ] 11. 归档格式（可选）
  - [ ]* 11.1 「导出全部数据」纳入交付物清单（optional）；密码保护 ZIP 评估
    - _Requirements: 3.1_

- [ ] 12. Final Checkpoint · 异构评估
  - [ ]* 12.1 OnlyOffice/程序表/自定义底稿 bulk 可行性评估（按业务优先级，不实现）
    - _Requirements: （范围外记录）_

## Notes

- 标 `*` 的子任务为 optional（Phase 2/3/4 + PBT/vitest 子任务）；按平台约定 optional(*) 任务仍需完成，仅排期靠后。
- 每条任务引用具体 requirements 子条款保证可追溯；每个 Correctness Property 对应 PBT 并标注属性号。
- **反假绿硬门槛**：MVP 4 场景以 Playwright 实测背书，不以单测绿为准。
- **复用清单**：路由真源 `acnr/manifest.list_import_export`；排序 `wp_bulk_tab_export._topological_sort`（已有 PBT）；Excel 执行层单表 I/E 端点；快照 version-trail；联动 `WORKPAPER_SAVED` 事件链；权限 `require_wp_edit_permission`。均不重写。
