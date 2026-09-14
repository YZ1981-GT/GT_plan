# 数据联动现状盘点

> P0-1 产出，2026-06 盘点

## 1. trace/linkage/stale 相关 Router

| Router 文件 | 前缀 | 说明 |
|---|---|---|
| `backend/app/routers/wp_trace.py` | `/api/projects/{pid}/workpapers/.../trace` | 底稿穿透（上游/下游） |
| `backend/app/routers/note_trace.py` | `/api/projects/{pid}/notes` | 附注穿透来源 |
| `backend/app/routers/report_trace.py` | `/api/projects/{pid}/reports/.../trace` | 报表穿透来源 |
| `backend/app/routers/cross_module_conflicts.py` | `/api/projects/{pid}/conflicts` | 跨模块冲突调解 |
| `backend/app/routers/event_cascade_health.py` | `/api/projects/{pid}/cascade-health` | 事件级联健康度 |

## 2. trace/linkage/stale 相关 Service

| Service 文件 | 核心类/函数 | 说明 |
|---|---|---|
| `linkage_service.py` | `LinkageService` | 联动日志/TB 变更记录/级联日志 |
| `unified_lineage_service.py` | `UnifiedLineageService` | 统一血缘查询（report_trace/wp_trace 委托） |
| `wp_trace_service.py` | `trace_upstream`/`trace_downstream` | 底稿上下游追溯 |
| `wp_note_linkage_service.py` | `WpNoteLinkageService` | 底稿↔附注联动 |
| `report_trace_service.py` | `ReportTraceService` | 报表穿透定位 |
| `stale_propagation_engine.py` | `StalePropagationEngine` | stale BFS 传播引擎 |
| `stale_summary_aggregate.py` | — | stale 汇总聚合 |
| `note_stale_service.py` | `StaleSection` | 附注 stale 节检测 |
| `prefill_engine.py` | `mark_stale` | 底稿预填数据过期标记 |
| `event_handlers.py` | `register_event_handlers` | 事件处理器集中注册 |
| `stale_degraded_logger.py` | `log_stale_degraded` | stale 降级记录（MVP 新增） |
| `linkage_contract_builder.py` | `build_tb_to_wp_contract` | LinkageContract 构建器（MVP 新增） |

## 3. 前端 Composable / 组件

| 文件 | 说明 |
|---|---|
| `composables/useStaleStatus.ts` | stale 状态查询（ReportView/DisclosureEditor/AuditReportEditor 共用） |
| `composables/useStaleRefresh.ts` | stale 刷新操作 |
| `composables/useStaleImpact.ts` | stale 影响范围查询 |
| `composables/useCrossModuleRefs.ts` | 跨模块引用（含手写路由跳转） |
| `composables/useResolveLinkageRoute.ts` | LinkageContract 路由解析（MVP 新增） |
| `components/common/TraceSourcePopover.vue` | 穿透来源弹窗 |
| `components/common/LinkageStatusBar.vue` | 联动状态条 |
| `components/LinkagePopover.vue` | 联动弹窗 |
| `components/LinkageBadge.vue` | 联动 badge |
| `components/StaleIndicator.vue` | stale 指示器 |
| `components/DegradedBanner.vue` | 降级状态横幅 |
| `components/workpaper/GtTraceabilityDialog.vue` | 底稿穿透对话框 |
| `components/notes/CellTraceDialog.vue` | 附注单元格穿透 |
| `views/composables/useReportTrace.ts` | 报表穿透 composable |

## 4. 手写路由跳转位置

### 4.1 wp_code 相关
- `useCrossModuleRefs.ts`：跨模块引用跳转含手写 `/projects/${pid}/workpapers/${wpId}` 路径
- `WorkpaperEditor.vue`：`wpDetail?.wp_code` 用于显示但不直接跳转
- `WorkpaperList.vue`：`wp_code` 用于列表展示和编辑路由

### 4.2 report row 相关
- `useReportTrace.ts`：`TraceLocation` 接口含 `row_code`，跳转逻辑在组件内
- `report_trace_service.py`：`report_trace_to_locate_targets` 返回定位列表

### 4.3 note section 相关
- `CellTraceDialog.vue`：附注单元格穿透，内部 fetch API 获取来源
- `note_trace.py` router：`/api/projects/{pid}/notes/{note_id}/cells/{cell_ref}/trace`

## 5. stale 静默 `pass` / 吞异常位置

| 位置 | 行 | 问题 |
|---|---|---|
| `event_handlers.py` `_mark_reports_stale_on_adjustment` | ~688 | AuditReport `is_stale` 更新 `except Exception: pass` — 静默吞掉 |
| `event_handlers.py` `_mark_workpapers_stale_all` | ~487 | `except Exception: logger.warning("Failed to mark workpapers stale")` — 仅 warning 无结构化记录 |
| `event_handlers.py` `_mark_workpapers_stale_by_account` | ~495 | `except Exception: logger.warning(...)` — 同上 |
| `event_handlers.py` `_on_workpaper_stale_detected` | ~813 | 空函数体仅 `logger.debug` — stale 传播未实现 |
| `event_handlers.py` `_on_workpaper_review_passed` | ~827 | 空函数体仅 `logger.debug` — 附注刷新未实现 |
| `event_handlers.py` `_on_cross_check_failed` | ~841 | 空函数体仅 `logger.debug` — 通知未实现 |

### 关键问题：`_mark_reports_stale_on_adjustment` 第 688 行

```python
try:
    await session.execute(
        _sa.update(AuditReport)...
    )
except Exception:
    pass  # AuditReport 可能没有 is_stale 字段
```

此处 `pass` 是 P0-4 要治理的核心目标：AuditReport.is_stale 字段不存在时静默跳过，不记录任何信息。

## 6. 现有 LinkageContract 基础设施（MVP 阶段产出）

- 后端 schema：`backend/app/schemas/linkage_contract.py`（Pydantic BaseModel，4 枚举 + 12 字段）
- 前端类型：`audit-platform/frontend/src/types/linkageContract.ts`（TypeScript 类型定义）
- 路由解析：`audit-platform/frontend/src/composables/useResolveLinkageRoute.ts`（workpaper/report/note/tb）
- 构建器：`backend/app/services/linkage_contract_builder.py`（TB→WP 单向）
- 降级记录：`backend/app/services/stale_degraded_logger.py`（内存记录器）
- 测试：3 个后端 + 1 个前端

## 7. 待 P0 补齐

- [ ] JSON Schema 参考文档
- [ ] 后端 `POST /api/projects/{pid}/linkage/resolve-route` API
- [ ] WP→Note、Note→Cell 的 LinkageContract 构建器
- [ ] 将 `event_handlers.py` 中 stale `pass` 改为调用 `log_stale_degraded`
- [ ] 前后端枚举一致性自动测试
