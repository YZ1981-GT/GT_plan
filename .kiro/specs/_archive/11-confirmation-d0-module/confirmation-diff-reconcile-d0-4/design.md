# Design Document

## Overview

为 D0-4 函证差异调节表创建**共享专用组件** `GtConfirmationDiffReconcile`（componentType=`confirmation-diff-reconcile`），核心设计是 **以"科目"列让一张底稿跨科目通用**（下拉标准科目 + 自定义），并在此基础上实现：差异自动计算 + 合计（可按科目分组）+ 从 D0-1 自动带入差异行 + 差异原因分析表按差异类型自动聚合 + 是否调整→下游联动（AJE/替代程序）+ 质量红线 + 看板。与 D0-1/D0-2/D0-3 同构，最大化复用其已建基础能力。

D0-4 与前三者的形态差异：D0-1/D0-2 是超宽表（→master-detail），D0-3 是叙事备忘录（→结构化填空+成稿预览）；D0-4 是**中等宽度的可计算明细表（约 11 列）**，无需 master-detail 拆分，主形态是"**单层可编辑网格 + 自动计算/聚合**"，重心在"科目列共享 + 差异/合计/分析表的自动派生 + D0-1 联动"。

## Architecture

```
htmlRendererRegistry 新注册：confirmation-diff-reconcile → GtConfirmationDiffReconcile
后端 _WP_CODE_OVERRIDE / render-config 对 D0-4 sheet 标 componentType=confirmation-diff-reconcile
（共享底稿：D0-4 在任一循环的 wp_code 均可映射到该 componentType，科目由行级"科目"列区分）

GtConfirmationDiffReconcile.vue（主组件）
├── props: wpId / sheetName / schema / htmlData / readonly
├── emit: save / open-formula / restore
│
├── DiffDashboard.vue        差异看板（总笔数/差异合计/已分析率/需调整/超重要性 + 类型分布 + 折叠）
├── DiffGrid.vue             差异明细网格（科目列下拉+自定义 / 差异自动算 / 合计行 / 按科目分组 / useCellSelection + 右键）
├── DiffAnalysisTable.vue    差异原因分析表（按差异类型自动聚合 笔数+金额，原因/应对可编辑）
├── DiffConclusion.vue       审计说明 + 审计结论（结论枚举 + 文本 + 未决事项提示）
│
├── useDiffReconcileData.ts  数据核心（rows/dirty/CRUD/差异auto/合计/分组小计/buildPayload/看板指标）
├── useDiffAnalysis.ts       差异原因分析表聚合（by diff_type → 笔数+金额+合计）
├── useD01DiffImport.ts      从 D0-1 拉取差异≠0 函证行 + 字段映射 + 按 confirm_index 去重
├── useCellSelection.ts      复用：选区/复制/粘贴/求和
├── CellContextMenu.vue      复用：右键菜单
├── useDictStore             复用：枚举（confirmation_subject / confirmation_diff_type / yes_no）
├── useExcelIO               复用：导入/导出
├── diffReconcileEnums.ts    枚举 dictKey 映射
└── diffReconcileTypes.ts    类型定义（DiffRow / DiffAnalysisRow / DiffMetrics）

共享底稿机制（需求 1）：componentType 科目无关；一张 D0-4 内多科目行共存，按"科目"列分组合计；
  下拉科目取 confirmation_subject 字典 + allow-create 自定义；跨循环复用（不绑定 D 循环）。

联动（需求 4/6）：上游 D0-1 经 useD01DiffImport 拉差异行；下游 是否调整=是→AJE 引用、未达账项/未回函→替代程序 D0-5/D0-6 跳转。均走既有跨底稿引用机制。

保存链路（复用既有）：emit('save', payload) → GtWpRenderer.onSave → WorkpaperEditor → POST /save
  payload = { rows, analysis, audit_note, conclusion, materiality_config, _format: 'diff-reconcile-v1' }

后端：system_dicts._DICTS 增 confirmation_subject + confirmation_diff_type；复用 yes_no
编制指引：backend/data/wp_guidance/D0-4.json 补准则程序文本（差异调查/错报与舞弊评估/替代程序触发条件）
```

## Components and Interfaces

### GtConfirmationDiffReconcile.vue（新，主组件）
- Props: `{ wpId, sheetName, schema, htmlData, readonly }`；Emit: `save / open-formula / restore`
- 旧格式（无 `_format`）降级 GtGridSheet 只读
- 布局：看板 → 差异明细网格 → 差异原因分析表（自动）→ 审计说明/结论

### DiffGrid.vue（新，核心）
- Props: `{ rows, readonly, groupBySubject }`；Emit: `field-change / add / delete / context-menu / import-d01`
- 11 列 el-table（科目下拉+自定义 / 索引号 / 被询证单位 / 账户交易 / 发函金额 / 回函金额 / 差异(只读自动) / 差异类型 / 差异原因 / 证据 / 是否调整）
- 合计行（发函/回函/差异）；groupBySubject=true 时每科目小计行 + 全表合计
- 金额列右对齐千分位 2 位小数（单位元）；差异=0 行淡化
- useCellSelection + CellContextMenu slot；工具栏（新增/删除/从D0-1带入/保存/导入/导出）

### DiffAnalysisTable.vue（新，需求 5）
- Props: `{ analysisRows, readonly }`；Emit: `note-change`
- 按差异类型行（时间性/记账/未达账项/其他 + 合计）：笔数+金额只读自动聚合，原因说明/应对措施可编辑

### DiffDashboard.vue（新）
- Props: `{ metrics, collapsed }`
- 总笔数/差异合计/已分析率/需调整笔数及金额/超重要性笔数 + 类型分布；异常高亮、可折叠

### DiffConclusion.vue（新，需求 8）
- Props: `{ auditNote, conclusion, hasPending }`；Emit: `change`
- 审计说明文本 + 审计结论（枚举 + 文本）；hasPending（差异未分析/调整未处理）时提示未决

### useDiffReconcileData.ts（新 composable）
```ts
interface DiffRow {
  id: string
  subject: string            // 科目（下拉 confirmation_subject + 自定义）
  confirm_index: string      // 询证函索引号（关联 D0-1）
  entity_name: string        // 被询证单位名称
  account_txn: string        // 账户/交易
  sent_amount: number | null // 发函金额（账面）
  reply_amount: number | null// 回函金额
  difference: number | null  // 差异 = sent - reply（只读自动）
  diff_type: string          // 差异类型（confirmation_diff_type）
  diff_reason: string        // 差异原因
  evidence: string           // 相关支持性证据/索引号
  need_adjust: string        // 是否调整（yes_no）
  adjust_ref: string         // 调整分录索引/处理说明（need_adjust=是 条件）
  remark: string
  _source?: 'd0-1' | 'manual'// 自动带入标识
}

useDiffReconcileData(htmlData, readonly) => {
  rows, addRow, deleteRow, updateField, importRows
  computeDifference(row)     // 差异 = sent - reply（精确小数）
  totals                     // computed: { sent, reply, diff }
  subjectSubtotals           // computed: Map<subject, {sent,reply,diff}>
  metrics                    // computed: 看板指标（总笔数/差异合计/已分析率/需调整/超重要性）
  dirty, buildPayload
}
```

### useDiffAnalysis.ts（新 composable，需求 5）
```ts
interface DiffAnalysisRow { diff_type: string; count: number; amount: number; note: string; action: string }
// amount = 该类型差异净额合计（带符号，与明细差异列同口径）；note/action 来自持久化 analysis_notes
useDiffAnalysis(rows, analysisNotes) => {
  analysisRows   // computed: 4 类型 + 合计；count=该类型差异行数，amount=该类型差异净额合计；note/action 取自 analysisNotes
  unclassified   // computed: 差异≠0 但 diff_type 空的笔数
}
// 仅 note/action 持久化（analysis_notes），count/amount 每次重算不入库
```

### useD01DiffImport.ts（新 composable，需求 4）
- `importFromD01()`：拉 D0-1 差异≠0 行 → 映射 DiffRow（confirm_index/entity_name/sent_amount←账面/reply_amount）→ 按 confirm_index 去重 → 标 `_source='d0-1'`
- D0-1 不可用 → 返回空 + 提示降级

## Data Models

### DiffRow（见上）/ DiffAnalysisRow（见上）

### DiffMetrics
```ts
{
  total: number              // 差异总笔数（差异≠0）
  diff_net_total: number     // 差异净额合计（带符号）
  diff_abs_total: number     // 差异绝对值合计（避免正负抵消误导）
  analyzed_rate: number      // 已分析率（已填原因/差异≠0）
  adjust_count: number; adjust_amount: number   // 需调整笔数/金额
  over_materiality_count: number                // 超重要性差异笔数
  type_dist: Record<string, number>             // 差异类型分布
}
```

### 重要性配置
```ts
{ materiality: number | null, source: 'B15-performance' | 'manual' }
// 默认取实际执行重要性（performance materiality，B15/Materiality 模块），可手填覆盖
```

### 保存载荷（`_format: 'diff-reconcile-v1'`）
`{ "_format": "diff-reconcile-v1", "rows": [DiffRow...], "analysis_notes": { "<diff_type>": {"note": "", "action": ""} }, "audit_note": "", "conclusion": {...}, "materiality_config": {...} }`
> 注：analysis 只持久化每类型的 note/action（可编辑部分）；笔数/金额为派生，加载后由 useDiffAnalysis 重算，不入库以防漂移。

## Correctness Properties

### Property 1: 差异自动计算
当 sent_amount 与 reply_amount 有值时，difference SHALL == sent_amount − reply_amount（精确小数，实时）；用户不可手填 difference。
**Validates: Requirements 3.1**

### Property 2: 合计与分组小计一致
totals.{sent,reply,diff} SHALL == 对应列所有行之和；按科目分组时各科目小计之和 SHALL == 全表合计（精确小数，无浮点漂移）。
**Validates: Requirements 3.2, 3.3, 3.5**

### Property 3: 差异原因分析表聚合一致
每个 diff_type 的 count SHALL == 明细中该类型差异行数，amount SHALL == 该类型差异净额合计（带符号）；分析表合计 SHALL == 各类型之和；明细变化后同 tick 重算；note/action 持久化，count/amount 重算不入库。
**Validates: Requirements 5.2, 5.3, 5.4**

### Property 4: 科目列下拉 + 自定义
科目列 SHALL 提供 confirmation_subject 枚举选项 + allow-create 自定义；自定义值保留并参与分组合计。
**Validates: Requirements 1.2, 1.3**

### Property 5: D0-1 带入去重与映射
从 D0-1 带入仅取**已回函且不符（差异≠0）**行，字段映射正确；已存在的 confirm_index SHALL 不重复带入；带入行标 `_source='d0-1'`；未回函行不带入（归替代程序）。
**Validates: Requirements 4.2, 4.3, 4.4, 4.7**

### Property 6: 是否调整派生下游
need_adjust=是 SHALL 计入需调整指标并提示填 adjust_ref；差异类型=未达账项 SHALL 提示替代程序跳转。
**Validates: Requirements 6.2, 6.3, 6.4**

### Property 7: 超重要性警示派生
当 |difference| ≥ materiality（有配置时）SHALL 红色警示并计入 over_materiality_count；无重要性配置时不误报。
**Validates: Requirements 7.3, 11.1**

### Property 8: 旧格式兼容
htmlData 无 `_format` 时降级 GtGridSheet 只读，不崩。
**Validates: Requirements 13.2**

### Property 9: 只读不可编辑
readonly=true 时所有控件不可编辑，工具栏增删/带入/保存/导入禁用，导出模板可用。
**Validates: Requirements 2.3, 10.5**

## Error Handling

- D0-1 不可用 → 带入降级提示，手工录入不阻塞
- 枚举字典缺失 → 降级 el-input
- 金额非数值 → 校验提示，差异/合计跳过该行不崩
- 重要性未配置 → 超重要性警示不触发（不误报）
- 导入缺列行 → 预览标错跳过，不中断
- 保存失败 → console.warn + dirty 保留
- 旧格式 → 降级只读网格

## Testing Strategy

- **useDiffReconcileData 单测**：CRUD + 差异自动算 + 合计/科目分组小计 + metrics + buildPayload（P1/P2/P7）
- **useDiffAnalysis 单测**：按类型聚合笔数+金额 + 合计 + 未分类计数 + 明细变化重算（P3）
- **useD01DiffImport 单测**：差异≠0 过滤 + 字段映射 + confirm_index 去重 + 降级（P5）
- **科目列 spec**：下拉枚举 + 自定义 allow-create + 自定义值参与分组（P4）
- **质量警示 spec**：差异未分析/缺证据/超重要性/疑似错报 警示触发（P6/P7）
- **审计结论 spec**：未决事项提示（差异未分析/调整未处理）
- **后端枚举测试**：confirmation_subject / confirmation_diff_type 返回完整
- **回归**：render-config 冒烟零回归
- **Playwright**：D0-4 从 D0-1 带入差异行 → 选科目（含自定义）→ 差异自动算 → 分类 → 分析表自动聚合 → 超重要性警示 → 标是否调整跳转 → 按科目分组合计 → 保存 → 重开持久化 + 跳 D0-1/D0-5/D0-6
