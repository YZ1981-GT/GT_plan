# 设计文档：平台数据联动契约、穿透与 stale 统一

## 概述

本 spec 将四表、序时账、试算表、调整分录、审定表、底稿、报表、附注、审计报告之间的联动收口为统一契约，解决当前穿透、stale、冲突、影响范围和路由跳转各模块自行实现的问题。

## 核心设计

### 1. LinkageContract

后端新增 `linkage_contract.py`，前端新增 `linkageContract.ts`，字段如下：

| 字段 | 说明 |
|---|---|
| `source_type` | tb / ledger / audit_sheet / workpaper / adjustment / report / note / attachment / ai |
| `source_id` | 来源对象 ID |
| `source_cell` | 来源单元格或字段 |
| `target_type` | 目标类型 |
| `target_id` | 目标对象 ID |
| `target_cell` | 目标单元格或字段 |
| `amount` | Decimal 字符串 |
| `basis` | 取数口径 |
| `status` | current / stale / conflict / manual_override |
| `confidence` | system / manual / ai_suggested / ai_confirmed |
| `route` | 前端可跳转路由 |
| `audit_log_id` | 留痕 ID |

### 2. LinkageFacade

新增后端 `linkage_facade_service.py`，封装现有：

- `linkage_service`
- `unified_lineage_service`
- `wp_note_linkage_service`
- `report_trace_service`
- `note_trace`
- `cross_module_conflicts`
- `stale_propagation_engine`

初期不删除旧服务，只在 UI 新入口和签发检查中使用 facade。

### 3. 前端统一穿透面板

新增/升级 `TraceSourcePopover` 为 `LinkageTraceDrawer`：

- 来源路径
- 取数口径
- 金额变动历史
- stale 状态
- 冲突状态
- 下游影响范围
- 一键跳转

### 4. 路由解析

新增 `resolveLinkageRoute(contract)`：

- `workpaper + wp_code`：调用 wp-id-by-code resolver 后跳转 `WorkpaperEditor`
- `note`：跳转附注编辑器并定位 section/table/cell
- `report`：跳转报表页并定位 row_code
- `attachment`：打开附件预览抽屉

### 5. stale 传播

stale 更新采用三层一致：

1. 后端状态字段或事件记录。
2. 前端 badge / banner。
3. 影响范围查询。

任何字段缺失或更新异常均记录到 `event_cascade_health`，不允许 `pass` 静默吞错。

### 6. 签发一致性清单

在合伙人签发页新增 checklist：

- 四表是否最新
- 调整分录是否已批准
- 审定表是否 stale
- 附注是否 stale
- 报告正文是否匹配意见类型
- AI 内容是否全部确认
- 关键附件是否存在

## 不在范围

- 不废弃现有 trace API。
- 不重写公式引擎。
- 不强制历史项目立即补全 lineage。

## 现有代码锚点

### 后端

- `backend/app/services/linkage_service.py`
- `backend/app/services/unified_lineage_service.py`
- `backend/app/services/wp_note_linkage_service.py`
- `backend/app/services/report_trace_service.py`
- `backend/app/services/stale_propagation_engine.py`
- `backend/app/services/stale_summary_aggregate.py`
- `backend/app/routers/cross_module_conflicts.py`
- `backend/app/routers/note_trace.py`
- `backend/app/routers/wp_trace.py`
- `backend/app/routers/report_trace.py`

### 前端

- `audit-platform/frontend/src/components/common/TraceSourcePopover.vue`
- `audit-platform/frontend/src/components/workpaper/LineageGraphPanel.vue`
- `audit-platform/frontend/src/composables/useCrossModuleRefs.ts`
- `audit-platform/frontend/src/composables/useStaleStatus.ts`
- `audit-platform/frontend/src/composables/useStaleRefresh.ts`
- `audit-platform/frontend/src/components/conflict/ConflictResolutionPanel.vue`

## API 草案

- `GET /api/projects/{project_id}/linkage/contracts`
- `GET /api/projects/{project_id}/linkage/trace?source_type=&source_id=&cell=`
- `GET /api/projects/{project_id}/linkage/impact?source_type=&source_id=`
- `POST /api/projects/{project_id}/linkage/resolve-route`
- `GET /api/projects/{project_id}/signoff/checklist`

## LinkageContract 示例

```json
{
  "source_type": "trial_balance",
  "source_id": "tb-row-id",
  "source_cell": "closing_balance",
  "target_type": "workpaper",
  "target_id": "wp-id",
  "target_cell": "D12",
  "amount": "123456.78",
  "basis": "TB closing balance after adjustment",
  "status": "current",
  "confidence": "system",
  "route": "/projects/{pid}/workpapers/{wp_id}",
  "audit_log_id": "log-id"
}
```

## 迁移策略

1. 保留现有 trace/linkage API。
2. 新 UI 入口统一走 LinkageFacade。
3. 先覆盖四表→底稿→附注最小链路。
4. 再覆盖附件、AI、交付件等扩展证据。

## 风险与回滚

- 风险：一次性生成全量 contract 成本过高。  
  回滚：按需查询，不做全项目预计算。
- 风险：旧 trace API 与新 contract 数据不一致。  
  回滚：显示新旧差异日志，P0 阶段以旧 API 为计算依据，新 contract 仅封装展示。
