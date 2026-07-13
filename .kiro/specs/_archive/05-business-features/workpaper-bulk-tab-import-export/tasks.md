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

- [x] 5. 路由 + 权限门禁
  - [x] 5.1 实现 `backend/app/routers/wp_bulk_router.py` 导出端点
    - `POST /export-templates`、`POST /export-data`（≥只读）；循环多选；返回 ZIP 或 task_id
    - 经 `router_registry` 注册
    - _Requirements: 1.1, 1.2, 3.1, 5.1, 5.2_
  - [x] 5.2 实现导入 + 回滚端点
    - `POST /import`（multipart ZIP，dryRun?、strategy；`require_wp_edit_permission`）；`POST /import/rollback`（项目经理）；只读/锁定项目拒绝导入
    - _Requirements: 2.3, 5.3, 5.4, 5.5_
  - [x] 5.3 SSE 进度端点
    - `GET /progress/{task_id}`（复用现有 SSE 模式）
    - _Requirements: 6.1_

- [x] 6. 前端三按钮 + 导入报告
  - [x] 6.1 实现 `WpBulkDialog.vue`
    - 三按钮（导出全部模板/导入全部数据/导出全部数据）+ 循环多选 + 冲突策略 radio + only_with_data 勾选 + DryRun 开关；与 `WpBatchExportDialog` 并列
    - _Requirements: 5.1_
  - [x] 6.2 实现 `WpBulkImportReport.vue`
    - 逐 sheet 表格（success/partial/failed/missing/unlisted/blocked_by_status/conflict_rejected + 行数 + 错误）；DryRun 与正式共用
    - _Requirements: 2.5, 8.4_
  - [x] 6.3 接入 SSE 进度条（复用现有组件）
    - _Requirements: 6.1_
  - [x] 6.4 导入导出 API composable
    - `useBulkTabImportExport.ts`：走 http(axios) 带 Authorization；ZIP 下载/上传（multipart）
    - _Requirements: 5.1, 5.2, 5.3_
  - [x]* 6.5 前端 vitest（组件挂载 + 报告状态渲染）
    - _Requirements: 5.1, 2.5_
  - [x] 6.6 Playwright D 循环往返实测（MVP 场景 1/2/3）
    - admin/admin123 → 导出 D 模板 ZIP → 填 3 张代表表 → 导入 → 数据一致 + D2-1↔D2-2 SUMIF 联动 + 回滚一致；0 console error
    - **✅ 已修复+Playwright 往返实测通过（2026-07-13，重启后端后验证）**。Playwright 揭示并修复 3 个真实 bug（均在 `_d2_import_export.py`，非本 spec 引入，属 D2 单表功能自身往返 bug）：①`import_data`/`export_data` 用 `wb.active` 读/写→模板首个 sheet 是"编制说明"→所有 sheet 导入误读说明 sheet + 导出数据误写说明 sheet；②D2-2 用 2 行合并表头与导入解析器（只读单行扁平表头）不兼容。**修复**：(a) 新增 `_select_data_ws(wb, sheet)` 按名选数据 sheet（跳过编制说明），import/export 均改用；(b) D2-2 模板改单行扁平表头 `get_d2_2_columns(segments)`（与导入解析器/`_d2_2_export_values` 同源）；(c) `_d_cycle_adapters._convert_import_response` 空表 warning→`skipped`（原误判 failed）。**回归守卫 `tests/test_d2_export_import_roundtrip.py` 8 测试全绿**。**Playwright 往返实测（重启后端）**：导出模板→flat 单行表头(39列含 6 账龄段×3期)→填 D2-2 一行→实写导入→**成功:1 跳过:2**（D2-2 成功 1 行，D2-3/D2-4 空表跳过）→postgres `D2-detail-rows` 落库确认(customerName/companyCode/priorUnadjusted 字段映射正确)→全程 0 console error。⚠️ 回滚场景(4)未单独 UI 实测（SnapshotGuard 单测覆盖，Task 3.2）。**🔴 dev 后端 run_uvicorn.py 无 --reload，改后端代码后需手动重启才生效**。
    - _Requirements: 2.1, 2.2, 4.1_

- [x] 7. Checkpoint · Phase 1（D 试点）+ PBT
  - ✅ MVP 场景 Playwright 实测通过（导出模板/导入实写/空表跳过，D2-2 落库确认，0 error）；`tests/test_d2_export_import_roundtrip.py`(8)+`test_bulk_import_export_properties_pbt.py`(14)+既有 bulk 测试全绿。回滚场景由 `test_bulk_import_service.py::test_all_or_nothing_rollback` 覆盖。
  - [x]* 7.1 编写 Correctness Property PBT（P1–P8）
    - ✅ `tests/test_bulk_import_export_properties_pbt.py`（14 测试全绿，`@settings(max_examples=5)`，逐条注 `Feature: workpaper-bulk-tab-import-export, Property {n}`）。P1 拓扑(薄引用,重 PBT 在 test_bulk_topological_sort_pbt.py)/P2 manifest 溯源 ACNR/P3 跳过隔离/P4 ConflictStrategy 三态/P5 DryRun 不写库/P6 回滚标记不变式/P7 WorkflowGate 门禁+权限/P8 zip_path 规范+无敏感信息。
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

- [x] 8. adapter 注册表扩 K/F/G/H
  - [x]* 8.1 扩 `IE_ADAPTER_REGISTRY` 到 K/F/G/H（ACNR manifest 已覆盖）
    - **🔵 补齐（2026-07-13 复盘用户提问「是否应扩到 I/J/K/L/M/N/S」）**：全仓实测发现 C24/E1/I1-I6/J1/J2/J3/L0 也有单表 I/E 端点（漏注册），且 **M/N/S 其实也有 I/E（独立路由 `m4_capital_reserve.py`/`n2_taxes_payable.py`/`s_estimate_calculation.py`，早先误判为无）**。已扩 `_kfgh_cycle_adapters._PREFIX_TO_MODULE` 补 C24-journal/E1/I1-I6/J1/J2/L0（wp_render_strategies 统一族，通用包装）+ J3 bespoke（异形路径 `/import-export/{template|export|import}`），注册表 59→**71** 项。测试新增 `test_j3_bespoke_registered` + `test_ceijl_endpoints_resolve`(11 参数化，验三端点路径可提取)全绿。**🔴 真实瓶颈非 adapter 而是 ACNR catalog**：`manifest.list_import_export` 只认 catalog 逐 sheet `import_export` 段(api_prefix/item_id/import_order/depends_on)，当前仅 D+F 启用→全部新注册 adapter 与 K/G/H 同为休眠待命。**剩余工作（独立任务，非本 spec）**：①ACNR catalog 逐 sheet 编写 import_export 段(贵的90%,数据任务)；②M/N/S 独立路由族 adapter 变体(路径 `/api/{module}/{wp_id}/{suffix}` 结构不同+api_prefix 由 catalog 命名决定,待敲定后 suffix-only 匹配补)。详见 `docs/proposals/bulk-tab-import-export-phase4-evaluation.md` §Task12.1 更正段。
    - ✅ 新建 `backend/app/services/bulk_tab/_kfgh_cycle_adapters.py`（镜像 `_d_cycle_adapters.py`）+ `register_kfgh_cycle_adapters()`，在 `bulk_tab/__init__.py` import 即注册。共登记 **52** 个 api_prefix（F×9 / G×21 / H×8 / K×14），全部指向既有单表 I/E 端点（复用，不重写列格式）。因 K/F/G/H 的 I/E 端点分「手写族 + 工厂族(`create_cycle_import_export_router`)」两类，统一用「按 `module.router` 路由后缀提取 endpoint 闭包 + 按签名传参」的通用包装覆盖两族，避免 52 份样板；复用 `_d_cycle_adapters` 的 `_read_streaming_response/_make_upload_file/_DUMMY_USER/_convert_import_response`（空表→skipped 语义）。测试 `tests/test_kfgh_cycle_adapters.py`（59 passed）：每 prefix 解析 + export/import callable + 幂等 + D 循环未丢 + 每循环一张 sheet 导出模板冒烟（f2-st/F2-24、g8/G8-3、h10/H10-2、k1/K1-5 均返回合法 xlsx）。get_diagnostics 全清。**🔴 manifest 覆盖实况**：当前 `global_catalog.json` 仅对 **F**（f2/f2-spe/f2-st/f2-val）启用 `import_export`，K/G/H 尚无 import_export 段 → 这 4 个 F prefix 为 manifest-live，其余 48 个已注册但处于 dormant（待 ACNR catalog 为 K/G/H 启用 import_export 后即生效，注册键为 inert dict 项，无副作用）。**round-trip 复核**：K/F/G/H 无 D2-2 式 bug——无任何模块 `create_sheet("编制说明", 0)`（编制说明均追加末尾，数据 sheet 保持 active）；g4/g6/g7/g8 的「multi」为多**worksheet**分区段导出（row1 标题/row2 表头，import 按 header_row=2 + 分区段名定位），非 D2-2 的单 sheet 多行合并表头，往返一致。
    - _Requirements: 7.1_
  - [x]* 8.2 逐循环 Playwright 往返回归
    - **实测范围说明（2026-07-13）**：D 循环全往返已实测（Phase1）。**F 导出经真实 UI 实测通过**（辽宁项目 d9295a0c，导出 F 模板→manifest 构建→ZIP 下载，0 error；该项目 51 张 F sheet 均未实例化为 I/E sheet 故全 skipped=fail-soft 正确）。F 导入/写入路径与 D **同一份通用包装代码**（`_kfgh_cycle_adapters` 签名感知调用），且 `test_kfgh_cycle_adapters.py`(59) 含 f2-st 模板导出冒烟(合法 xlsx)。**K/G/H 休眠**：ACNR `global_catalog.json` 仅 D(46)+F(51) 启用 `import_export`，K/G/H 无 I/E 段→manifest 不产出→bulk 层不触达（adapter 已注册待命）。**启用 K/G/H 属 ACNR catalog 数据任务，不在本 spec 范围**。无 F-data 项目可做填充往返（import 路径已由 D + 单测背书）。
    - _Requirements: 2.1, 2.2_

### Phase 3 · 异步/审计强化（Wave 7，optional `*`）

- [x] 9. 异步任务 + 审计看板
  - [x]* 9.1 大项目异步导出/导入（复用 batch-export-async）+ all-or-nothing 开关 + 审计日志汇总
    - ✅ 新建 `backend/app/services/bulk_tab/bulk_async_runner.py`：后台 worker 用**自有 AsyncSession**（`async_session_factory()`，绝不复用请求 session）+ GC-safe `_BACKGROUND_TASKS` 集合（对齐 `consol_refresh_job_service` 范式）。`schedule_export`/`schedule_import` 触发即返回 task_id，`_run_export`/`_run_import` 后台跑 `bulk_export_service.export`/`bulk_import_service.run`，进度经既有 `bulk_progress_service`（内存状态 + SSE 队列，不占 asyncpg）推送；导出 total 由预建 manifest 计数、导入 total 由预读 ZIP manifest 文件数回填。**结果落地**：导出 ZIP 写 `storage/bulk_exports/{task_id}.zip`，导入 ImportReport 存内存 `task.result`。`bulk_progress.py` 扩 `result_path`/`result_filename`/`result` 字段 + `set_total`/`set_result_path`/`set_result` 方法。**路由新增 5 端点**（`wp_bulk_router.py`，均经既有 deps 门禁）：`POST /export-templates/async`、`POST /export-data/async`（≥只读）、`GET /export/{task_id}/download`（≥只读，FileResponse RFC5987）、`POST /import/async`（编制权 + `all_or_nothing` Form 参 → `AtomicityMode.ALL_OR_NOTHING`，Req 4.2；只读/锁定门禁）、`GET /import/{task_id}/result`（≥只读）。**all-or-nothing 全回滚 + 审计日志汇总由既有 `bulk_import_service.run` 内部处理**（Task 3.2/4.4 已实现），异步层仅透传 `atomicity`。测试 `tests/test_bulk_async_runner.py`（7 passed）：导出 happy(total 回填/落盘/complete)/failure(fail 标记)、导入 happy(run 调用/commit/result 存储)/all-or-nothing 透传/user 不存在→fail、schedule_* 返回 task_id。既有 bulk 回归 101 passed。10 路由注册确认。
    - _Requirements: 6.1, 6.2, 4.2_

### Phase 4 · 契约守卫 + 异构评估（Wave 7–8，optional `*`）

- [x] 10. manifest 契约 CI 守卫
  - [x]* 10.1 CI drift guard：校验 manifest 字段 100% 来自 ACNR catalog
    - ✅ `tests/test_bulk_manifest_acnr_drift_guard.py`（4 测试全绿）：AST 扫描 `build_manifest` 取数符号 ⊆ ACNR 白名单(list_export_sheets/list_import_export/list_sheets)+源码禁 open/json.load/wp_account_mapping/SHEET_COLUMNS 等非 ACNR 数据源+路由字段全 `entry.get()` 动态取(防硬编码)+catalog 不可用必 raise(≥3处,不静默降级)。与 P2 运行期 PBT 互补(行为层 vs 防漂移层)。
    - _Requirements: 7.1, 7.2_

- [x] 11. 归档格式（可选）
  - [x]* 11.1 「导出全部数据」纳入交付物清单（optional）；密码保护 ZIP 评估
    - ✅ 评估完成 → `docs/proposals/bulk-tab-import-export-phase4-evaluation.md` §Task 11.1。结论：**纳入交付物清单建议实现**（复用 `ExportTask`/`DeliverableService` + 新增 `bulk_workpaper_data` doc_type，异步导出完成回调登记，归档项目留最后快照，工作量小）；**密码保护 ZIP 建议默认关闭**（stdlib `zipfile` 不支持加密写，AES-256 需引 `pyzipper` 第三方库→违反不引新依赖偏好；常规场景权限门禁 + TLS 已覆盖机密性；仅涉密离线交付合规要求出现时作独立增量实现，当前不实现仅记录方案）。
    - _Requirements: 3.1_

- [x] 12. Final Checkpoint · 异构评估
  - [x]* 12.1 OnlyOffice/程序表/自定义底稿 bulk 可行性评估（按业务优先级，不实现）
    - ✅ 评估完成 → `docs/proposals/bulk-tab-import-export-phase4-evaluation.md` §Task 12.1。结论：三类异构底稿 bulk 往返**均不纳入 bulk-tab**。①**OnlyOffice**（原生 xlsx/docx，整文件替换语义无行级 ConflictResolver）→ 批量导出走既有 `batch-export`（按 wp_id 打包原生文件），批量导入无结构化合并语义不实现；②**程序表**（a-program-console，auto_data_source 运行时实时取数 + field_overrides 多维，导出静态 xlsx 再导入会破坏实时一致性）→ 价值在系统内联动，离线往返违背设计不实现；③**自定义底稿**（无 ACNR catalog 登记 / 无单表 I/E 三端点）→ manifest 唯一真源是 ACNR，不在 catalog 则 fail-soft 跳过 `no_adapter`（正确行为），需批量须前置纳入 ACNR + 提供单表 I/E，属独立 feature。核心原则：bulk-tab 是「结构化底稿行级数据」编排层，非「任意文件批量搬运」。
    - _Requirements: （范围外记录）_

## Notes

- 标 `*` 的子任务为 optional（Phase 2/3/4 + PBT/vitest 子任务）；按平台约定 optional(*) 任务仍需完成，仅排期靠后。
- 每条任务引用具体 requirements 子条款保证可追溯；每个 Correctness Property 对应 PBT 并标注属性号。
- **反假绿硬门槛**：MVP 4 场景以 Playwright 实测背书，不以单测绿为准。
- **复用清单**：路由真源 `acnr/manifest.list_import_export`；排序 `wp_bulk_tab_export._topological_sort`（已有 PBT）；Excel 执行层单表 I/E 端点；快照 version-trail；联动 `WORKPAPER_SAVED` 事件链；权限 `require_wp_edit_permission`。均不重写。
