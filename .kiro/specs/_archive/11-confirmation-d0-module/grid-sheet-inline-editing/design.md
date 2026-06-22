# Design Document

## Overview

为 D0-1 函证结果汇总表创建专用 Vue 组件 `GtConfirmationSummary`（componentType=`confirmation-summary`），替代当前的 GtGridSheet 只读网格。组件按 6 个功能区块垂直排布：科目 Tab + 汇总看板 + master-detail 明细 + 样本选择 + 审计说明 + 审计结论。编制说明移到 wp_guidance 侧栏。

## Architecture

```
htmlRendererRegistry 新注册：confirmation-summary → GtConfirmationSummary
后端 _WP_CODE_OVERRIDE / render-config 对 D0-1 的 sheet 标 componentType=confirmation-summary

GtConfirmationSummary.vue（主组件）
├── props: wpId / sheetName / schema / htmlData / readonly
├── emit: save / open-formula / restore
│
├── 视图切换：列表视图(默认) / 完整表格视图（localStorage 记忆，两视图共享 useConfirmationData）
├── ConfirmationTabs.vue        科目 Tab 切换
├── ConfirmationDashboard.vue   汇总看板（折叠式，5 科目×7 指标）
├── 【列表视图】ConfirmationMaster.vue + ConfirmationDetail.vue（master-detail）
├── 【完整表格视图】ConfirmationFullGrid.vue（28 列宽表，沿用 GtGridSheet 美化 + useCellSelection 选区/复制/粘贴/求和 + 列类型可编辑）
├── ConfirmationSampling.vue    样本选择表单（折叠区）
├── ConfirmationNotes.vue       审计说明 5 专题 textarea（折叠区）
├── ConfirmationConclusion.vue  审计结论 radio+textarea（折叠区）
│
├── useConfirmationData.ts      数据核心 composable（两视图共享）
│   ├── rows: Ref<ConfirmationRow[]>       明细行响应式数组
│   ├── summary / sampling / notes / conclusion  其他区块状态
│   ├── computed: dashboardMetrics         汇总看板指标（按科目实时聚合 + 覆盖率/确认率）
│   ├── computed: accountTabs              科目 Tab 列表（从 rows 去重）
│   ├── computeConfirmedAmount(row)        可确认金额业务规则（函证方式×回函×相符）
│   ├── addRow / deleteRow / updateField   行操作
│   ├── importRows(parsed)                 批量导入
│   ├── buildPayload()                     保存载荷
│   └── dirty: Ref<boolean>
│
├── useConfirmationAutoFetch.ts 自动取数（TB 账面 / D0-2 或抽样带入 / 索引号生成）
├── useExcelIO（复用）            导入清单 / 导出模板
├── useCellSelection.ts         复用：选区/复制/粘贴/求和/右键（完整表格视图）
├── confirmationEnums.ts        枚举 dictKey 常量映射
└── confirmationTypes.ts        TypeScript 类型定义

保存链路（复用既有）：
  emit('save', payload) → GtWpRenderer.onSave → WorkpaperEditor → POST /save
  payload = { rows, summary_config, sampling, notes, conclusion, _format: 'confirmation-v1' }

后端：
  system_dicts._DICTS 增 6 个枚举 key
  _WP_CODE_OVERRIDE 或 render-config dispatch 对"函证结果汇总表D0-1" → confirmation-summary
```

## Components and Interfaces

### GtConfirmationSummary.vue（新，主组件）
- Props: `{ wpId, sheetName, schema, htmlData, readonly }`
- Emit: `save(payload)` / `open-formula({sheetName})` / `restore`
- 职责：组装 6 个子组件 + 接入 useConfirmationData + 传递 readonly

### ConfirmationTabs.vue（新）
- Props: `{ tabs: string[], active: string }`
- Emit: `change(tab)`
- 渲染：el-tabs type="card"，含"全部"选项

### ConfirmationDashboard.vue（新）
- Props: `{ metrics: DashboardMetrics, collapsed: boolean }`
- 渲染：5 科目×7 指标网格（el-descriptions 或自定义 grid），异常标红/橙

### ConfirmationMaster.vue（新）
- Props: `{ rows: ConfirmationRow[], readonly, expandedRowId }`
- Emit: `expand(rowId)` / `add` / `delete(ids)` / `context-menu({row,event})`
- 渲染：el-table 7 列 + 多选 + 工具栏（新增/删除/保存）
- 接入 useCellSelection（复用右键/复制/求和）+ CellContextMenu（slot 注入行操作）

### ConfirmationDetail.vue（新）
- Props: `{ row: ConfirmationRow, readonly, enumOptions }`
- Emit: `field-change({rowId, field, value})`
- 渲染：4 阶段折叠区（el-collapse），条件 v-show 由 row.is_replied 驱动

### ConfirmationSampling.vue（新）
- Props: `{ data: SamplingData, readonly }`
- Emit: `change(field, value)`
- 渲染：折叠区内 6 个 textarea/select

### ConfirmationNotes.vue（新）
- Props: `{ data: NotesData, readonly }`
- Emit: `change(index, value)`
- 渲染：折叠区内 5 个带标题的 textarea（placeholder 含示例）

### ConfirmationConclusion.vue（新）
- Props: `{ selected: 'A'|'B'|'C'|null, text: string, readonly }`
- Emit: `change({selected, text})`
- 渲染：el-radio-group(A/B/C) + v-show(B/C) textarea

### ConfirmationFullGrid.vue（新，完整表格视图）
- Props: `{ rows: ConfirmationRow[], readonly, enumOptions }`
- Emit: `field-change` / `add` / `delete` / `paste`
- 渲染：28 列宽表（原生 table 或 el-table），沿用 GtGridSheet 美化（分组表头 5 色着色 / 冻结首列 / 斑马纹 / 空值淡化）
- 单元格按列类型可编辑（enum→el-select / number→el-input-number / text→el-input / 只读→span）
- 接入 useCellSelection：单击/Ctrl/Shift/拖拽框选 + 复制(TSV+HTML) + 粘贴 + 多选求和
- CellContextMenu slot：复制 / 粘贴 / 求和 / 插入行(上下) / 删除行 / 复制索引号
- 与列表视图共享同一 useConfirmationData.rows（编辑互通）

### useConfirmationData.ts（新 composable）
```ts
interface ConfirmationRow {
  id: string; seq: number; index_no: string
  sample_purpose: string; entity_name: string
  account_type: string; amount: number | null
  confirmation_method: string; send_date: string; send_no: string
  address: string; address_verified: string
  is_replied: string; reply_method: string; is_matched: string
  reply_date: string; reply_tracking: string; reply_address: string
  address_consistent: string
  reply_amount: number | null; difference: number | null
  confirmed_amount: number | null; reconcile_index: string
  other_notes: string
  has_alternative: string; alt_confirmed: number | null
  alt_unconfirmed: number | null; alt_index: string
  conclusion: string
}

useConfirmationData(htmlData, readonly) => {
  rows, addRow, deleteRow, updateField
  accountTabs, activeTab
  dashboardMetrics (computed, 按 account_type 分组聚合)
  sampling, notes, conclusionData
  dirty, buildPayload
}
```

### 数据格式（保存载荷 `_format: 'confirmation-v1'`）
```json
{
  "_format": "confirmation-v1",
  "rows": [ ConfirmationRow... ],
  "summary_config": { "account_balances": {"应收账款": 1234567, ...} },
  "sampling": { "population": "...", "specific": "...", "method": "随机选样", ... },
  "notes": ["控制说明...", "误差分析...", "传真可靠性...", "不符事项...", "替代程序..."],
  "conclusion": { "selected": "A", "text": "" }
}
```

## Data Models

### ConfirmationRow（28 字段，见 Components 节）

### DashboardMetrics
```ts
Record<string, {  // key=科目名
  balance: number         // 账面金额（TB 自动取 or 用户填）
  sent_amount: number     // 发函金额 = SUM(该科目 rows.amount)
  sent_ratio: number      // 函证覆盖率 = 发函/账面
  reply_confirmed: number // 回函确认金额
  reply_ratio: number     // 回函可确认占发函%
  alt_confirmed: number   // 替代确认金额
  confirm_coverage: number // 确认覆盖率 = (回函确认+替代确认)/账面 ← 质量红线
  total_ratio: number     // (回函+替代)占账面%
  warn_level: 'ok'|'warn'|'danger'  // 确认覆盖率<80%=danger, 覆盖率<50%=warn
}>
```

### 可确认金额业务规则（computeConfirmedAmount）
```
相符        → confirmed = amount
不符        → confirmed = reply_amount（差异待 D0-4）
未回+消极式  → confirmed = amount（视同认可）
未回+积极式  → confirmed = alt_confirmed（须替代程序）
difference = amount - reply_amount（相符强制 0）
用户手工覆盖 → 标记 _overridden，不再自动算
```

### 自动取数来源（useConfirmationAutoFetch）
- 账面金额：`GET trial_balance` 该科目审定额（按 account_type 映射标准科目）
- 函证清单带入：D0-2 parsed_data 已核实单位 / 抽样底稿样本行 → 被询证单位+科目+金额
- 索引号：`{wp_code}-{序号补零}` 自动生成
- 字段来源标识：`_source: 'auto'|'manual'` 控制视觉区分

### SamplingData / NotesData / ConclusionData
简单 struct，见 Sampling/Notes/Conclusion 组件 Props。

## Correctness Properties

### Property 1: 汇总看板实时性
明细行任何增删/修改后，dashboardMetrics 在同一 tick 内重算，无需手动触发或保存。
**Validates: Requirements 3.2**

### Property 2: 条件字段一致性
当 `is_replied` 从"是"改为"否"时，回函相关字段（reply_method/is_matched/reply_date/reply_tracking/reply_address/address_consistent/reply_amount）SHALL 保留值但不显示；重新改回"是"时恢复显示。不清除用户已填数据。
**Validates: Requirements 2.2, 2.3**

### Property 3: 派生字段正确性
`difference = amount - reply_amount`，当任一为 null 时 difference = null；当 `is_matched = '相符'` 时强制 difference = 0。
**Validates: Requirements 2.4, 2.5**

### Property 4: 旧格式兼容
当 htmlData 为旧 grid cells 格式（无 `_format`）时，组件 SHALL 降级为 GtGridSheet 只读渲染（不崩）。
**Validates: Requirements 12.2**

### Property 5: 只读不可编辑
readonly=true 时所有表单/列表/textarea 不可编辑，工具栏增删/保存禁用。
**Validates: Requirements 1.5, 9.6**

### Property 6: 双视图数据一致
列表视图与完整表格视图共享同一 useConfirmationData.rows；在任一视图编辑后切换视图，另一视图 SHALL 显示相同数据（编辑互通，dirty 一致）。
**Validates: Requirements 13.4**

### Property 7: 可确认金额规则正确性
对任意行，computeConfirmedAmount 满足：相符→=amount；不符→=reply_amount；未回+消极式→=amount；未回+积极式→=alt_confirmed。用户覆盖后 `_overridden=true` 则不再自动算。
**Validates: Requirements 17.1**

### Property 8: 导入不破坏既有行
importRows 追加新行（序号续接），不修改/删除已有行；缺列行被跳过且报告，不抛异常。
**Validates: Requirements 16.3, 16.4**

## Error Handling

- D0-2 引用查询失败 → entity_name 降级为 el-input 自由输入
- 枚举字典缺失 → 降级 el-input
- 保存失败 → console.warn + dirty 保留供重试
- 旧格式解析 → 降级只读网格

## Testing Strategy

- **useConfirmationData 单测**：addRow/deleteRow/updateField + dashboardMetrics 实时性 + buildPayload 格式
- **条件字段 spec**：is_replied 切换时 detail 区域正确显示/隐藏
- **汇总看板 spec**：增删行后指标立即变化 + 异常标色
- **后端枚举测试**：6 个 dictKey 完整返回
- **回归**：render-config 冒烟零回归
- **Playwright**：D0-1 科目 Tab 切换 → 新增行 → 填枚举 → 保存 → 重开验证持久化
