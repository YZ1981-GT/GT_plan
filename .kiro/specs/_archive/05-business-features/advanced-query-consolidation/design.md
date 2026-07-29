# Design Document

## Overview

高级查询三处不一致的收敛，实证后确定为**纯前端收敛**（不改后端 execute 契约）：抽三个共享前端模块（列标签映射 / xlsx 导出工具 / 源 URI 解析纯函数），让 `CustomQueryDialog.vue`（业务视图）、`CustomQueryTab.vue`、`AdvancedQueryBuilder.vue` 三方复用，消除硬编码孤本与并行实现。附带收益：CustomQueryTab / AdvancedQueryBuilder 由此获得中文列标签（此前显示英文 key）。

## Architecture

```
新增共享模块（src/components/query/）
  queryColumnLabels.ts   ← 收敛 CustomQueryDialog.COLUMN_LABELS，单一真源 + resolveColumnLabel 三级兜底
  queryExport.ts         ← 共享 xlsx 导出纯工具（列标题=标签、取值=key、统一文件名）
  querySourceUri.ts      ← 共享 URI 构造/wp 解析纯函数 + 失败提示常量

消费方（复用，不改后端）
  CustomQueryDialog.vue  → columnLabel/exportResult/jumpToCell/onTraceToTemplate 委托三模块
  CustomQueryTab.vue     → displayColumns.title / onExportExcel 委托
  AdvancedQueryBuilder.vue → resultColumns.title / doExport 文件名对齐（保留后端 blob 导出）

后端：不改。execute 契约（columns=string[]）保持不变。
```

**关键决策**：

1. **列标签放前端单一真源，不改 execute 契约**（决策依据：后端 execute 各 `_query_*` 返回 `string[]` 英文 key、无 title；中文标签属展示层关注点）。`resolveColumnLabel(key, title?)` 三级兜底：共享映射命中 → 后端下发的 `title`（若存在且 `!== key`）→ `key` 原样。这样即便未来后端补 title 也自动生效，当前 string[] 场景走共享映射。
2. **导出：Dialog/Tab 收敛为共享前端 xlsx 工具；Builder 保留后端 `query/export-excel`**（大数据经后端流式更稳），仅对齐文件名规则与列标题口径。不把 Builder 强改为前端 xlsx（避免大数据前端 OOM 回归）。
3. **跳转/溯源不合并目标**（cell_ref→WorkpaperEditor 实际数据格；溯源→模板库模板详情，语义不同），只抽共享 URI 构造/wp 解析纯函数 + 统一失败提示文案常量，消除重复代码。
4. **零 DB / 零后端改动**：本 spec 全部改动在前端 3 新模块 + 3 组件接线 + 测试。

## Components and Interfaces

### queryColumnLabels.ts（新增）

```ts
// 单一真源：列 key → 中文标签（收敛自 CustomQueryDialog.COLUMN_LABELS，补齐 Tab/Builder 常见列）
export const QUERY_COLUMN_LABELS: Record<string, string>
// 三级兜底：共享映射 → title(若非空且≠key) → key
export function resolveColumnLabel(key: string, title?: string): string
```

### queryExport.ts（新增）

```ts
export interface QueryExportInput {
  columns: string[]            // 列 key 顺序
  rows: Record<string, any>[]  // 结果行
  labelFn?: (key: string) => string  // 缺省用 resolveColumnLabel
  fileName: string             // 已按调用方规则拼好（含项目/源/年度）
  sheetName?: string           // 默认「查询结果」
}
// 前端 xlsx 导出（动态 import('xlsx')），列标题=labelFn(key)、取值=row[key] ?? ''
export async function exportQueryResultToXlsx(input: QueryExportInput): Promise<void>
// 文件名清洗（去非法字符 + 去 emoji），供 Dialog/Tab/Builder 统一拼名
export function sanitizeExportName(s: string): string
```

### querySourceUri.ts（新增）

```ts
// wp_code + sheet + cell → 'workpaper:D2|审定表D2-1|B7'（cell/sheet 可空）
export function buildWorkpaperUri(wpCode: string, sheetName?: string, cellRef?: string): string
// 结果行 + 当前 source → 溯源 URI（复用 onTraceToTemplate 原推断逻辑）
export function buildTraceUri(row: Record<string, any>, selectedSource: string): string
// 统一失败提示文案
export const RESOLVE_FAIL_MSG: { wpNotFound: (code: string) => string; notRegistered: string; noUri: string }
```

### 组件接线（复用）

- **CustomQueryDialog.vue**：删除内联 `COLUMN_LABELS`，`columnLabel` 委托 `resolveColumnLabel`；`exportResult` 委托 `exportQueryResultToXlsx`（文件名沿用现规则经 `sanitizeExportName`）；`jumpToCell`/`onTraceToTemplate` 的 URI 构造委托 `querySourceUri`（跳转目标与提示不变）。
- **CustomQueryTab.vue**：`displayColumns` 的 `title` 经 `resolveColumnLabel(key, meta.title)`；字段选择 checkbox 标签同样中文化；`onExportExcel` 委托 `exportQueryResultToXlsx`。
- **AdvancedQueryBuilder.vue**：`resultColumns` title 经 `resolveColumnLabel`；`doExport` 文件名经 `sanitizeExportName` 对齐（保留 `query/export-excel` blob 路径）。

## Data Models

本 spec **无新增数据库表/列、无后端模型变更**（零 DB / 零后端）。仅新增前端 TypeScript 接口类型：

- `QueryExportInput`（见 queryExport.ts）：`{ columns: string[]; rows: Record<string,any>[]; labelFn?; fileName: string; sheetName? }` — 导出工具入参。
- `RESOLVE_FAIL_MSG`（见 querySourceUri.ts）：失败提示文案常量对象。
- 复用既有 `QueryColumnMeta`（`useAcnrDrill.ts`：`{key,title,addrId,drillable,dtype}`），不新增列元数据结构。

execute 响应仍为既有 `{ rows: any[]; columns: string[]; total: number; error? }`，本 spec 不改其形状。

## Correctness Properties

### Property 1: 标签解析三级兜底
**Validates: Requirements 1.1, 1.4**
`resolveColumnLabel(key, title)`：key 在共享映射 → 返回映射中文；否则 title 非空且 `!==key` → 返回 title；否则返回 key。未知 key 永不返回空/报错。

### Property 2: 标签映射单一真源
**Validates: Requirements 1.2, 4.4**
`CustomQueryDialog` 不再存在内联 `COLUMN_LABELS` 定义；三组件的列/字段标签均经 `resolveColumnLabel`。

### Property 3: execute 契约不变
**Validates: Requirements 1.3, 4.1**
本 spec 不修改 `custom_query.py` 的 execute 请求/响应；`TestExecuteContractBaseline` 全绿。

### Property 4: 导出列标题与取值
**Validates: Requirements 2.1**
`exportQueryResultToXlsx` 生成的 aoa：首行 = `columns.map(labelFn)`（中文标题），数据行 = `columns.map(c => row[c] ?? '')`（按 key 取值）。

### Property 5: 导出实现收敛
**Validates: Requirements 2.2, 4.4**
`CustomQueryDialog.exportResult` 与 `CustomQueryTab.onExportExcel` 均委托 `exportQueryResultToXlsx`，无各自的 `XLSX.utils.aoa_to_sheet` 重复实现。

### Property 6: 文件名规则一致
**Validates: Requirements 2.3**
三方导出文件名经 `sanitizeExportName` 清洗（去 `\/:*?"<>|` 与 emoji），Builder 保留后端 blob 但文件名口径对齐。

### Property 7: URI 构造纯函数正确
**Validates: Requirements 3.1**
`buildWorkpaperUri('D2','审定表D2-1','B7') === 'workpaper:D2|审定表D2-1|B7'`；sheet/cell 缺省时正确省略分隔段。

### Property 8: 跳转目标与失败提示不变
**Validates: Requirements 3.2, 3.3, 3.4, 3.5**
cell_ref 下钻仍跳 `WorkpaperEditor`(+highlight)，右键溯源仍跳 `/template-library`；解析失败提示走 `RESOLVE_FAIL_MSG` 统一文案；既有可跳转场景全部保持。

## Error Handling

- 标签：`resolveColumnLabel` 对 undefined/空 key 返回空串兜底不抛错。
- 导出：无数据 `ElMessage.warning('无数据')` 并 return（现行为保留）；`import('xlsx')` 失败由调用方 try/catch。
- URI/跳转：`wp-id-by-code` 无结果 → `RESOLVE_FAIL_MSG.wpNotFound(code)`；`address-resolve` 未注册 → `RESOLVE_FAIL_MSG.notRegistered`；无法推断 URI → `RESOLVE_FAIL_MSG.noUri`。

## Testing Strategy

- **vitest 纯逻辑**：`queryColumnLabels.spec.ts`（Property 1/2）、`queryExport.spec.ts`（Property 4/6，构造 aoa/文件名，mock `xlsx`）、`querySourceUri.spec.ts`（Property 7）。
- **零回归门**：后端 `test_advanced_query_hardening_wave012.py::TestExecuteContractBaseline` 全绿（Property 3）；三组件 get_diagnostics 全清 + `curl.exe` Vite transform 200。
- **Playwright（关键路径）**：业务视图与高级构建器列名一致（中文）、导出 xlsx、cell_ref 下钻跳转、右键溯源跳转（Property 8）。
