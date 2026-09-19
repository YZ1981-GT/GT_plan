# Design Document

## Overview

把 N1-5「可用以后年度税前利润弥补的亏损检查表」从自造 roll-forward 模型重建为源模板结构（按可抵扣亏损**到期年度**列示、本期数三列、确认／不确认拆分、依据、是否充足、来源三选、检查底稿索引），并把「不确认」金额与原因作为附注（上市 `五、30` / 国企 `八、31`）未确认一节中**可弥补亏损部分**的单一数据源。

设计原则：

1. **不新造机制**：附注推送继续走既有 `sync_from_workpaper` + `n1NoteSectionMap.buildN1SyncPayload`（子表键／列头不变，仅换喂入语义）；跨表键继续用 `N1-5-total-recognizable`；导入导出继续走 `n1_deferred_tax_assets.py` 的 `_SUPPORTED_SHEETS` 单一注册表。
2. **新键旁挂、旧键保留**：新模型持久化到新键（`N1-5-rows` / `N1-5-lead-rows`），旧键 `N1-5-loss-rows` 只读不删，作为迁移来源与回溯依据。
3. **禁止推算冒充判断**：附注未确认一节只反映审计师在 N1-5 的确认／不确认录入；无数据时为空（不再用 `deriveUnrecognizedFromLoss` 的「未弥补 − 已确认基数」推算）。
4. **共用章节所有权不变**：`五、30` / `八、31` 四张子表 owner 仍是 N1（见 spec `n1-disclosure-note-linkage` Decision 1 方案 A），N3 不推这两张共用表。

## Architecture

### 数据流

```
源模板结构
   │
   ▼
N1-5 结构化视图 ──(录入)──► useN1LossCheck（新模型）
   │                             │
   │  矩阵视图(判断矩阵/点选)     ├─ persist ─► allResponses['N1-5-rows']（JSON 数组）
   │                             │             allResponses['N1-5-lead-rows']（引导行）
   │                             │
   │                             ├─ 派生 ─► auditedAmount / unrecognizedAmount /
   │                             │          recognizableAsset / isExpired / 合计
   │                             │
   │                             └─ Cross_Keys ─► 'N1-5-total-recognizable'（remark，语义不变）
   │                                                 │
   │                                                 ▼
   │                                    useN1CrossSheet.lossCheckToCalcTable ─► N1-4 展示
   │
   ├─「从 N1-5 带入可弥补亏损」─► N1-4 行（仅填空）
   └─「从 N1-5 带入」──────────► N1-1「可抵扣亏损」分类行（仅该行）

附注取数（同一 workbook，同一 allResponses）
   allResponses['N1-5-rows']
        │
        ▼
   useN1DisclosureSource.deriveUnrecognizedLossPayload()   ← 新增（单一入口）
        │   rows: [{ expiryYear, unrecognized, priorUnrecognized, reason }]
        │   totals / hasData
        ▼
   N1TabDisclosureListed / N1TabDisclosureSoe
        │  组装 N1DisclosureSnapshot:
        │    unrecognizedRows += { item:'可抵扣亏损', amount: totalUnrecognized, priorAmount: totalPrior }
        │    lossExpiryRows    = payload.rows（不确认口径）
        ▼
   n1NoteSectionMap.buildN1SyncPayload（子表键/列头不变）
        ▼
   POST /api/disclosure-notes/{pid}/sync-from-workpaper → 附注模块渲染
```

### 迁移路径（Legacy_Loss_Row → Loss_Row）

```
allResponses['N1-5-loss-rows']（旧，保留）
        │  检测：新键为空 且 旧键有行
        ▼
   页面顶部 el-alert「检测到旧版 N1-5 数据（N 行），可一键带入」
        │  审计师确认
        ▼
   migrateLegacyLossRows(legacy, auditYear)（纯函数，幂等）
        │  可映射：到期年度=亏损年度+弥补年限 / 本期账面=亏损−已弥补 /
        │          依据=recognitionBasis / 确认金额=原可确认基数 / 税率
        │  不猜测：上期不确认 / 审计调整 / 是否充足 / 来源三选 / 检查底稿索引 留空
        ▼
   allResponses['N1-5-rows']（新键落库，旧键不删）
```

## Components and Interfaces

### 1. `composables/useN1LossCheck.ts`（重建）

```ts
export interface UseN1LossCheckOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  formData: ReturnType<typeof useN1FormData>
  /** 审计年度（Req 2.1：禁止用 new Date().getFullYear()） */
  auditYear: Ref<number>
}

export function useN1LossCheck(o: UseN1LossCheckOptions): {
  /** 到期年度行（派生后） */
  rows: ComputedRef<N1LossComputedRow[]>
  /** 引导行（期末未分配利润 / 其中：可抵扣亏损） */
  leadRows: ComputedRef<N1LossLeadComputed[]>
  totals: ComputedRef<N1LossTotals>
  /** 行级勾稽/合规提示（不阻断保存） */
  warnings: ComputedRef<N1LossWarning[]>
  /** 旧版数据检测（Req 6.1） */
  legacyInfo: ComputedRef<{ count: number; canImport: boolean }>

  addRow(expiryYear: number): void
  removeRow(index: number): void
  updateRow(index: number, field: EditableLossField, value: unknown): void
  updateLead(key: N1LossLeadKey, field: EditableLeadField, value: unknown): void
  /** 一键带入旧版数据（幂等，按到期年度去重） */
  importFromLegacy(): number
}
```

要点：

- 派生列（`auditedAmount` / `unrecognizedAmount` / `recognizableAsset` / `isExpired` / `remainingYears`）全部 computed，不落库；持久化只存录入字段（与 `useN1DisclosureSource` 重算同源，Req 1.3）。
- `isExpired = expiryYear < auditYear`（Req 2.1/2.2）；届满行 `recognizableAsset = 0`，且 `recognizedAmount` 被强制视为 0（Req 3.5、Property 3）。
- `unrecognizedAmount = auditedAmount − effectiveRecognized`（`recognizedAmount` 是唯一录入侧，Req 3.1）。
- `_persist()`：`debouncedSave('N1-5-rows', { conclusion: JSON.stringify(rows) })` + `saveField('N1-5-total-recognizable', { remark })`（Req 5.1，键与语义不变）。
- 异步 hydrate：`watch(allResponses, immediate)` + 一次性 guard（与既有范式一致）。

### 2. `n1/calc/N1TabLossCheck.vue`（重建结构化视图 + 复用矩阵视图）

- 主表列按源模板顺序呈现；派生列 `formula-col` 虚线 + tooltip 标注公式来源。
- 点选控件（Req 1.6）：`是否充足` = `el-select`（是／否）、来源三选 = 三个 `el-checkbox`。
- 新增行：`ElMessageBox.prompt` 先要到期年度（4 位年份）再建行（Req 1.4）。
- 顶部：旧版数据检测 alert（Req 6.1）+ 行级勾稽提示（Req 1.5 / 3.2 / 2.4）。
- 底部：引导行区（期末未分配利润 / 其中：可抵扣亏损）+ 合计区（确认／不确认／上期不确认／本期审定）+ 回填按钮（N1-4 / N1-1）。
- 矩阵视图沿用已落地的 `N1LossJudgmentMatrix.vue`，本特性扩为**可点选**（`readonly=false` 时点击色块切换 `sufficient` 与来源三选），并把判断项列换为源模板语义：`弥补期限是否届满` / `到期前是否有足够应纳税所得额` / `来源：生产经营所得` / `来源：应纳税暂时性差异` / `来源：其他` / `依据是否已填` / `检查底稿索引是否已填`。

### 3. `n1/calc/N1LossJudgmentMatrix.vue`（扩展）

```ts
const props = defineProps<{ rows: N1LossComputedRow[]; readonly?: boolean }>()
const emit = defineEmits<{
  (e: 'locate', index: number): void
  (e: 'toggle', payload: { index: number; field: 'sufficient' | 'sourceOperating' | 'sourceTemporaryDiff' | 'sourceOther' }): void
}>()
```

- `readonly` 时保持现有只读色块行为（零回归）。

### 4. `composables/useN1DisclosureSource.ts`（新增单一入口，旧函数标记 deprecated）

```ts
export const N1_LOSS_ROWS_KEY_V2 = 'N1-5-rows'

export interface N1UnrecognizedLossRow {
  expiryYear: string        // '2027'
  unrecognized: number      // 本期不确认金额（审定口径）
  priorUnrecognized: number // 上期不确认金额
  reason: string            // 依据 / 不确认原因
}

export interface N1UnrecognizedLossPayload {
  rows: N1UnrecognizedLossRow[]   // 按到期年度聚合、升序
  totalUnrecognized: number
  totalPriorUnrecognized: number
  hasData: boolean                // 新键无行 → false（Req 4.4 / Property 9）
}

export function deriveUnrecognizedLossPayload(
  allResponses: Map<string, any>,
): N1UnrecognizedLossPayload
```

- `hasData=false` 时 `rows=[]`、合计为 `0` 但调用方按 `hasData` 决定是否输出（附注侧写 `null`，不写 0）。
- `deriveUnrecognizedFromLoss`（旧推算）保留但仅在**新键无行且旧键有行**时作为兼容读数，并在返回值上带 `isLegacyEstimate: true` 供 UI 提示；新键有行时永不使用。

### 5. 两个附注 tab（`N1TabDisclosureListed.vue` / `N1TabDisclosureSoe.vue`）

- 未确认一节的「可弥补亏损」行与「亏损到期」表改由 `deriveUnrecognizedLossPayload` 供数；`hasData=false` 时该节展示 `el-alert`「待 N1-5 编制」，`amount` 传 `null`（`buildN1SyncPayload` 的 `nz()` 保证不塌 0）。
- 「可抵扣暂时性差异」部分来源不变（Req 4.5）。
- `sync-from-workpaper` 请求体不变（子表键／`columns` 由 `n1NoteSectionMap` 决定），仅 `snapshot.unrecognizedRows` / `snapshot.lossExpiryRows` 的取数改变。

### 6. 事件通道（复用，Req 4.2 / 5.4）

- N1-5 保存后沿用既有 `eventBus.emit('loss-check:recognizable-updated', …)`；本特性**为其补上消费者**（N1-4 刷新），不新增无消费者事件。
- 附注刷新沿用既有 `disclosure:note-text-updated` / 底稿保存后的 `refreshDisclosureFromWorkpapers` 链路。

### 7. 后端 `routers/n1_deferred_tax_assets.py`（IE Sheet_Spec 更新）

`_SUPPORTED_SHEETS['N1-5']` 更新为新列：

| 列头 | field | 类型 |
|---|---|---|
| 到期年度 | `expiryYear` | int |
| 上期不确认递延所得税资产的可弥补亏损 | `priorUnrecognized` | num |
| 本期账面金额 | `bookAmount` | num |
| 本期审计调整 | `auditAdjustment` | num |
| 确认递延所得税资产的可弥补亏损 | `recognizedAmount` | num |
| 适用税率 | `taxRate` | num |
| 依据 | `basis` | text |
| 到期前是否有足够的应纳税所得额 | `sufficient` | 是/否 |
| 其中：来源于生产经营所得 | `sourceOperating` | √ |
| 其中：来源于以前期间产生的应纳税暂时性差异 | `sourceTemporaryDiff` | √ |
| 其中：来源于其他原因 | `sourceOther` | √ |
| 检查底稿索引 | `indexRef` | text |
| 备注 | `remark` | text |

- `item_id` 由 `N1-5-loss-rows` 改为 **`N1-5-rows`**（前端新读取键，Req 7.2）；`storage_field='conclusion'`；`_SHEET_ROW_ID_PREFIX['N1-5']='loss-'` 保持。
- 派生列（本期审定金额、不确认金额、可确认递延税资产）**不出现在导入列**；导出数据时可作为只读附加列输出但解析时忽略。
- `sufficient` 解析：`是/Y/y/yes/√` → `'yes'`，`否/N/n/no` → `'no'`，空 → `''`。
- 来源三选解析：`√/是/Y/1/TRUE` → `true`，其余 → `false`。

## Data Models

### Loss_Row（新，前端持久化于 `N1-5-rows`）

```ts
export type N1LossSufficiency = 'yes' | 'no' | ''

export interface N1LossRow {
  id: string                    // 'loss-{n}'
  /** 可抵扣亏损到期年度（源模板行标识） */
  expiryYear: number
  /** 亏损发生年度（可选，仅参考/迁移回溯） */
  lossYear?: number | null
  /** 上期不确认递延所得税资产的可弥补亏损 */
  priorUnrecognized: number
  /** 本期数 — 账面金额 */
  bookAmount: number
  /** 本期数 — 审计调整 */
  auditAdjustment: number
  /** 确认递延所得税资产的可弥补亏损（唯一录入侧） */
  recognizedAmount: number
  /** 适用税率（平台扩展列：源模板无，但可确认递延税资产需要），小数如 0.25 */
  taxRate: number
  /** 依据（不确认>0 时必填提示） */
  basis: string
  /** 到期前是否有足够的应纳税所得额 */
  sufficient: N1LossSufficiency
  sourceOperating: boolean
  sourceTemporaryDiff: boolean
  sourceOther: boolean
  /** 检查底稿索引 */
  indexRef: string
  /** 备注（弥补年限特殊政策说明等，Req 2.3） */
  remark?: string
}

export interface N1LossComputedRow extends N1LossRow {
  /** 本期审定金额 = bookAmount + auditAdjustment */
  auditedAmount: number
  /** 有效确认额：届满行恒 0 */
  effectiveRecognized: number
  /** 不确认金额 = auditedAmount − effectiveRecognized（下限 0） */
  unrecognizedAmount: number
  /** 可确认递延所得税资产 = effectiveRecognized × taxRate */
  recognizableAsset: number
  /** expiryYear < auditYear */
  isExpired: boolean
  /** max(0, expiryYear − auditYear) */
  remainingYears: number
  /** sufficient==='no' 且仍有确认额 → 提示 */
  sufficiencyConflict: boolean
  /** unrecognizedAmount > 0 且 basis 为空 */
  basisMissing: boolean
  /** effectiveRecognized + unrecognizedAmount ≠ auditedAmount（浮点容差 0.01） */
  splitMismatch: boolean
}
```

### Lead_Rows（引导行，持久化于 `N1-5-lead-rows`）

```ts
export type N1LossLeadKey = 'retainedEarnings' | 'deductibleLoss'

export interface N1LossLeadRow {
  label: string        // '期末未分配利润' / '其中：可抵扣亏损'
  priorUnrecognized: number
  bookAmount: number
  auditAdjustment: number
  remark?: string
}
// computed: auditedAmount = bookAmount + auditAdjustment
```

### Totals

```ts
export interface N1LossTotals {
  priorUnrecognized: number
  bookAmount: number
  auditAdjustment: number
  auditedAmount: number
  recognized: number
  unrecognized: number
  recognizableAsset: number
}
```

### 存储键一览

| 键 | 字段 | 内容 |
|---|---|---|
| `N1-5-rows` | `conclusion` | `N1LossRow[]`（新） |
| `N1-5-lead-rows` | `conclusion` | `Record<N1LossLeadKey, N1LossLeadRow>`（新） |
| `N1-5-total-recognizable` | `remark` | 可确认递延税资产合计（**不变**，Cross_Keys） |
| `N1-5-loss-rows` | `conclusion` | Legacy_Loss_Row（只读，不删） |
| `N1-5-recognition-basis` / `N1-5-audit-conclusion` | — | 说明/结论（`formData.setField('5', …)`，不变） |

### 迁移纯函数

```ts
export function migrateLegacyLossRows(
  legacy: readonly LegacyLossRow[],
  auditYear: number,
  existing: readonly N1LossRow[] = [],
): { rows: N1LossRow[]; added: number; skipped: number }
```

- 按 `expiryYear` 去重：`existing` 已含该年度 → skip（幂等，Property 7）。
- `expiryYear = lossYear + maxYears`；`bookAmount = max(0, lossAmount − recoveredBegin − currentRecovery)`；`auditAdjustment = 0`；
  `recognizedAmount = isExpired ? 0 : min(bookAmount, futureTaxableIncome)`；`basis = recognitionBasis`；`taxRate = taxRate || 0.25`；
  `lossYear` 保留。
- `priorUnrecognized = 0`、`sufficient = ''`、来源三选 `false`、`indexRef = ''`（Property 8：不猜测）。

## Correctness Properties

### Property 1: 本期审定 = 账面 + 审计调整

对任意 `bookAmount`、`auditAdjustment`，`auditedAmount === round2(bookAmount + auditAdjustment)`；引导行同规则。

**Validates: Requirements 1.2, 1.3, 9.1**

### Property 2: 确认 + 不确认 = 本期审定

对任意行，`effectiveRecognized + unrecognizedAmount === auditedAmount`（容差 0.01）；当录入 `recognizedAmount > auditedAmount` 时 `unrecognizedAmount` 下限为 0 且 `splitMismatch === true`。

**Validates: Requirements 3.1, 1.5, 9.1**

### Property 3: 届满行确认额恒为 0

`expiryYear < auditYear` ⇒ `effectiveRecognized === 0` ∧ `recognizableAsset === 0` ∧ `unrecognizedAmount === auditedAmount`，与录入的 `recognizedAmount` 无关。

**Validates: Requirements 2.2, 3.5, 9.1**

### Property 4: 可确认递延税资产 = 确认金额 × 税率

`recognizableAsset === round2(effectiveRecognized * taxRate)`；合计 `totals.recognizableAsset === round2(Σ recognizableAsset)`。

**Validates: Requirements 3.4, 9.1**

### Property 5: 不确认合计 = 附注未确认一节可弥补亏损合计

`deriveUnrecognizedLossPayload(allResponses).totalUnrecognized === round2(Σ unrecognizedAmount)`，且等于 `buildN1SyncPayload` 中亏损到期子表合计行的 `end`。

**Validates: Requirements 4.1, 4.3, 9.1**

### Property 6: 到期年度聚合幂等且不丢金额

同一 `expiryYear` 的多行经 payload 聚合后条数为 1，其 `unrecognized` 等于该年度各行之和；聚合前后总额相等。

**Validates: Requirements 4.1, 4.3**

### Property 7: 历史迁移幂等

`migrateLegacyLossRows(legacy, y, migrateLegacyLossRows(legacy, y, []).rows)` 的 `added === 0`，且 rows 与首次结果逐字段相等。

**Validates: Requirements 6.2, 6.4, 9.1**

### Property 8: 迁移不猜测

迁移产出的每一行 `priorUnrecognized === 0` ∧ `sufficient === ''` ∧ 三个来源标记均为 `false` ∧ `indexRef === ''` ∧ `auditAdjustment === 0`。

**Validates: Requirements 6.3**

### Property 9: 无数据时附注该节为空而非 0

`N1-5-rows` 缺失或为空数组 ⇒ `hasData === false` ∧ `rows.length === 0`；附注侧 `unrecognizedRows` 对应金额为 `null`（`buildN1SyncPayload` 输出 `null` 而非 0）。

**Validates: Requirements 4.4, 9.1**

### Property 10: 届满判定基于审计年度

同一组行在 `auditYear = Y` 与 `Y + 1` 下，`isExpired` 集合单调扩张（`Y` 下届满的在 `Y+1` 下仍届满），且不依赖系统当前年。

**Validates: Requirements 2.1, 2.2**

### Property 11: IE Round_Trip 字段逐字对应

后端 `_export_row → _parse_row` 往返后每个可编辑字段逐字相等；`expiryYear` 为 `int`（不出现 `2023.0`）；`sufficient` ∈ `{'yes','no',''}`；三个来源标记为 `bool`；派生列不出现在解析结果里。

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 12: 跨表键不回退

任一保存后 `allResponses['N1-5-total-recognizable'].remark` 等于 `String(totals.recognizableAsset)`，`useN1CrossSheet.lossCheckToCalcTable` 读到的值与 Property 4 一致。

**Validates: Requirements 5.1, 8.1**

## Error Handling

| 场景 | 行为 |
|---|---|
| `N1-5-rows` JSON 解析失败 | 返回空数组 + `console.warn`，不抛错；旧键仍可作为迁移来源（fail-open） |
| 迁移时旧键 JSON 损坏 | `legacyInfo.canImport = false`，提示「旧版数据无法解析，请人工补录」 |
| 到期年度重复新增 | `addRow` 允许（同年度多笔亏损合法），聚合层按年度合并（Property 6） |
| `recognizedAmount > auditedAmount` | 不阻断保存，`splitMismatch` 提示（Req 1.5） |
| `sufficient === 'no'` 但确认额 > 0 | 不自动搬移金额，仅 `sufficiencyConflict` 提示（Req 2.4） |
| 附注取数时 `hasData === false` | 附注该节 `el-alert` 提示「待 N1-5 编制」；同步 payload 该节金额为 `null`（不写 0） |
| IE 导入某行到期年度非 4 位年份 | 该行跳过并计入 `warnings`，其余行照常导入 |
| AI 生成失败 | 沿用 `generateN1Text` 既有 fail-open（无文本则不回填） |

## Testing Strategy

1. **纯函数单测（vitest）**：`useN1LossCheck` 的派生规则（Property 1-4、10）、`migrateLegacyLossRows`（Property 7-8）、`deriveUnrecognizedLossPayload`（Property 5-6、9）。
2. **契约测试**：`buildN1SyncPayload` 在 `hasData=false` 时子表金额为 `null`（Property 9）；子表键／`columns` 键集合与既有快照一致（零回归，Req 8.2）。
3. **后端契约测试**：`_SUPPORTED_SHEETS['N1-5']` 的 `item_id === 'N1-5-rows'`、headers 与 `_FIELD_MAPS` 一致、`expiryYear` 为整数字段、Round_Trip（Property 11）。
4. **跨表回归**：`N1-5-total-recognizable` 写入与 `useN1CrossSheet` 读取（Property 12）；N1-4 / N1-1 带入只填空不覆盖。
5. **零回归门**：既有 `n1-contract.spec.ts` / `n1-integration.spec.ts` / `test_n1_deferred_tax_assets_integration.py` 全绿；因结构变更必须调整的断言在任务中标注为 basis 改变。
6. **live Round_Trip（可选）**：真实项目鉴权 HTTP `create → verify → cleanup`，断言导入后 `N1-5-rows` 有值且字段逐字对应，附注 `五、30` 未确认一节子表 rows 与合计正确；结束恢复原状。
