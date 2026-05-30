---
spec: gt-c-note-table-shrink
status: draft
version: v1.0
created: 2026-05-30
---

# 设计文档：GtCNoteTable / GtEControlTest 超级 SFC 拆分

## 设计原则

1. **机械拆分优先**：尽可能"剪切-粘贴"原代码到新文件，不重写逻辑——降低引入 bug 的概率
2. **状态归属 shell**：响应式状态（`ref`）留在 shell，composable 接收 ref/getter 作为入参（保持单一数据源，避免状态副本）
3. **顶层同名暴露**：凡测试 `vm.xxx` 访问的成员（需求 13 清单），shell 必须顶层声明/解构同名绑定——两组件均**无 defineExpose**，测试靠 @vue/test-utils 的 setupState 代理访问 setup 顶层绑定（仅测试环境），故绑定必须在 setup 顶层作用域
4. **子组件无副作用**：子组件只负责渲染 + emit，不持有 saveTimer、不直接发 API
5. **增量可回滚**：每个产物一次 commit，拆完即跑测试

## 目标文件结构

### GtCNoteTable（1803 行 → 1 shell + 3 子组件 + 3 composable + 1 types）

```
components/workpaper/
├── GtCNoteTable.vue              shell ≤450（header/switcher/context/子表遍历/refs/cross-ref/sync）
├── GtCNoteTable.types.ts         21 类型（需求 1 清单）
├── cnote/
│   ├── CNoteCell.vue             单元格渲染器（原内联 defineComponent，8 分支）≤250
│   ├── CNoteSubTableCard.vue     单张子表卡片（static/dynamic + 工具栏 + footer）≤450
│   └── CNoteInheritanceBadge.vue 联动校验徽标 UI ≤120
└── composables/
    ├── useCNoteFormula.ts        cellComputedValue/footerTotalColumns/footerTotalValue ≤200
    ├── useCNoteInheritance.ts    evaluateRule/computeRuleSource/computeRuleTarget/filterRows + ruleStatuses ≤250
    └── useCNotePersist.ts        initData/buildSavePayload/debounceSave ≤200
```

### GtEControlTest（1414 行 → 1 shell + 4 子组件 + 1 composable + 1 types）

```
components/workpaper/
├── GtEControlTest.vue            shell ≤350（header + test_type 路由 + refs + 共用 helper）
├── GtEControlTest.types.ts       13 类型（需求 8 清单）
└── econtrol/
    ├── EControlSummaryTable.vue  summary 子模式 ≤320
    ├── EControlSingleForm.vue    single 子模式 ≤280
    ├── EControlEvalStepper.vue   evaluation_step 子模式 ≤350
    ├── EControlAiPanel.vue       AI 建议面板（3 模式复用）≤180
    ├── FieldInput.vue            字段输入控件（原内联 defineComponent，single/eval 共用）≤120
    ├── econtrolHelpers.ts        safeEvaluate/stepLabel/stepShortTitle/hintTableRows 纯函数
    └── composables/
        └── useEControlConclusion.ts  deriveSuggestion/deriveConfidence/onConclusionChange ≤200
```

> 注：目录 `cnote/` `econtrol/` 为新建子目录，避免 workpaper/ 根目录文件爆炸；测试 import 路径相应调整（需求 13 允许）。

---

## 一、GtCNoteTable 拆分详细设计

### 1.1 GtCNoteTable.types.ts（需求 1）

纯类型搬运，从原文件 364-525 行剪切 21 个类型定义到独立文件，全部 `export`。shell 与子组件 `import type { ... } from './GtCNoteTable.types'`。

```ts
export type SubTableType = 'static_rows' | 'dynamic_rows'
export type ColumnType = 'text' | 'textarea' | 'number' | 'enum' | 'multi_enum' | 'date' | 'boolean'
export type RenderHint = 'amount' | 'amount_formula' | 'percent' | 'percent_formula'
  | 'checkmark' | 'tag' | 'index_chip' | string
export type SubClass = 'listed' | 'soe'
export interface ColumnDef { /* 原样 */ }
export interface ColumnDefWithKey extends ColumnDef { _cellKey: string }
// ... StaticRowDef / FooterTotalDef / SubTableSchema / InheritanceRuleSourceTarget
// ... InheritanceRule / VersionVariant / ContextField / CrossRefDef
// ... LinkageDownstreamRule / LinkageDef / CNoteTableSchema / RowData
// ... CNoteTableHtmlData / SyncPayload / RuleStatus
```

### 1.2 CNoteCell.vue（需求 2）

原 577-731 行内联 `defineComponent` 转为 SFC。保留 `<script setup>` + render function（`h`）形态或转为模板——**采用 render function 形态**（保持轻量函数式渲染、零行为差异）。

```ts
// CNoteCell.vue <script setup lang="ts">
import { h } from 'vue'
import { ElInput, ElInputNumber, ElSelect, ElOption, ElCheckbox, ElDatePicker } from 'element-plus'
import { formatAmount } from '@/utils/formatAmount'
import { isLabelField, formatPercent } from './cnoteHelpers'  // 见 1.2.1
import type { ColumnDefWithKey, RowData } from '../GtCNoteTable.types'

const props = defineProps<{
  row: RowData
  col: ColumnDefWithKey
  readonly?: boolean
  computedValue?: number | string | null
}>()
const emit = defineEmits<{ change: [value: any] }>()
// render function 内 8 分支逐字搬运（onUpdate 改 emit('change', v) + p.row[col.field]=v）
```

**8 渲染分支**（不可遗漏，对应需求 2 AC-1）：
1. `col.readonly || isLabelField` → 只读 span（含 `_indent` 缩进 class）
2. `render === 'amount_formula'` → 只读 `gt-amt` + formatAmount(computedValue)
3. `render === 'percent_formula'` → 只读 + formatPercent(computedValue)
4. `type === 'boolean'` → ElCheckbox
5. `type === 'number'` → ElInputNumber（amount 时 precision=2 + gt-amt + controlsPosition right）
6. `type === 'enum'` → ElSelect 单选 clearable
7. `type === 'multi_enum'` → ElSelect multiple collapseTags
8. `type === 'date'` → ElDatePicker（YYYY-MM-DD）/ `textarea` → ElInput textarea / 默认 → ElInput text

#### 1.2.1 cnoteHelpers.ts（新建，承载共享纯函数）

`isLabelField` / `formatPercent` / `escapeNumber` / `genRowId` 四个纯函数被 CNoteCell、useCNoteFormula、shell 共用，抽到 `cnote/cnoteHelpers.ts` 避免重复。逐字搬运原 733-775 行实现。

### 1.3 useCNoteFormula.ts（需求 4）

```ts
export function useCNoteFormula(subTableData: Ref<Record<string, RowData[]>>) {
  function cellComputedValue(st: SubTableSchema, row: RowData, col: ColumnDefWithKey): number | null { /* 原 976-1011 */ }
  function footerTotalColumns(st: SubTableSchema): ColumnDef[] { /* 原 1012-1025 */ }
  function footerTotalValue(st: SubTableSchema, col: ColumnDef): number { /* 原 1026-1045 */ }
  return { cellComputedValue, footerTotalColumns, footerTotalValue }
}
```

- 入参 `subTableData` 为 shell 的同一个 ref（footerTotalValue 内部读 `subTableData.value[st.id]`）
- 依赖 `escapeNumber`（从 cnoteHelpers import）
- 无状态、纯函数，最易单测（需求 13 AC-4 要求 ≥5 用例）

### 1.4 useCNoteInheritance.ts + CNoteInheritanceBadge.vue（需求 5）

**composable**：
```ts
export function useCNoteInheritance(
  schema: Ref<CNoteTableSchema>,
  subTableData: Ref<Record<string, RowData[]>>,
  currentStandardSubClass: Ref<SubClass>,
) {
  const ruleStatuses = computed<RuleStatus[]>(() => { /* 遍历 inheritance_rules + applicable_when 过滤 + evaluateRule */ })
  function evaluateRule(rule): RuleStatus | null { /* 原 1052-1121 */ }
  function computeRuleSource(rule): number | null { /* 原 1122-1148 */ }
  function computeRuleTarget(rule): number | null { /* 原 1149-1160 */ }
  function filterRows(rows, src): RowData[] { /* 原 1161-1187 */ }
  function ruleStatusForSubTable(stId: string): RuleStatus[] { return ruleStatuses.value.filter(r => r.subTableId === stId) }
  return { ruleStatuses, ruleStatusForSubTable }
}
```

- **关键**：`ruleStatuses` 必须在 shell 顶层解构（`const { ruleStatuses, ruleStatusForSubTable } = useCNoteInheritance(...)`），因测试 `vm.ruleStatuses` 直接访问（需求 13 清单）
- `ruleStatusTagType` / `ruleStatusIcon` 是纯展示映射，移入 `CNoteInheritanceBadge.vue` 内部

**badge 子组件**：
```ts
// CNoteInheritanceBadge.vue
const props = defineProps<{ statuses: RuleStatus[] }>()
// 渲染 el-tooltip + el-tag（ruleStatusTagType 颜色 + ruleStatusIcon 图标 + rs.label）
```
shell 中 `<CNoteInheritanceBadge :statuses="ruleStatusForSubTable(st.id)" />`

### 1.5 useCNotePersist.ts（需求 6）

```ts
export function useCNotePersist(opts: {
  props: { wpId: string; sheetName: string; htmlData: CNoteTableHtmlData; readonly?: boolean }
  subTableData: Ref<...>; hiddenSubtables: Ref<string[]>
  currentStandardSubClass: Ref<SubClass>; contextData: Ref<...>
  sectionId: Ref<string>
  emit: (e: 'save', data: CNoteTableHtmlData) => void
}) {
  let saveTimer: ReturnType<typeof setTimeout> | null = null
  function initData() { /* 原 1380-1453：从 htmlData 还原 4 部分状态 */ }
  function buildSavePayload(): CNoteTableHtmlData { /* 原 1455-1487 */ }
  function debounceSave() { /* 原 1488+：readonly 短路 + 1.5s 防抖 + emit('save', buildSavePayload()) */ }
  onBeforeUnmount(() => { if (saveTimer) clearTimeout(saveTimer) })
  return { initData, buildSavePayload, debounceSave }
}
```

- saveTimer 封装在 composable 内（含 onBeforeUnmount 清理，需求 6 AC-3）
- shell 把所有相关 ref 传入，composable 不复制状态

### 1.6 CNoteSubTableCard.vue（需求 3）

```ts
const props = defineProps<{
  subTable: SubTableSchema
  rows: RowData[]               // subTableData[st.id]
  readonly?: boolean
  visibleColumns: ColumnDefWithKey[]   // shell 计算后传入（standard 过滤结果）
  cellComputedValue: (st, row, col) => number | null  // 注入 useCNoteFormula
  footerColumns: ColumnDef[]
  footerValue: (col: ColumnDef) => number
  reachedMax: boolean
}>()
const emit = defineEmits<{
  'cell-change': [row: RowData, col: ColumnDefWithKey]
  'add-row': []
  'remove-row': [index: number]
}>()
```

- 渲染 static_rows（el-table + CNoteCell）/ dynamic_rows（工具栏新增行 + el-table + 删除列 + footer 合计）
- 不持有 saveTimer：增删行 / cell 变更 → emit 给 shell → shell 调 debounceSave（需求 3 AC-4）
- shell 中 `<CNoteSubTableCard v-for="st in visibleSubTables" :key="st.id" ... @cell-change="onCellChange" @add-row="onAddDynamicRow(st)" @remove-row="i => onRemoveDynamicRow(st, i)" />`

### 1.7 GtCNoteTable.vue shell（需求 7）

shell 保留：
- **template**：header（实体/期间/章节/索引 + standard switcher）+ context 表单 + 隐藏子表恢复区 + `<el-collapse>` 遍历 `<CNoteSubTableCard>` + `<CNoteInheritanceBadge>` + cross_refs 来源区 + 同步 footer
- **refs**（顶层声明，测试访问）：`subTableData` / `hiddenSubtables` / `contextData` / `currentStandardSubClass` / `activeCollapse` / `isSyncing` / `sectionId`(computed) / `schema`(props)
- **composable 顶层解构**：`useCNoteFormula` / `useCNoteInheritance`（暴露 ruleStatuses）/ `useCNotePersist`（暴露 initData/debounceSave）
- **shell 内保留函数**（1-3 个，不独立）：`onStandardSwitch`（ElMessageBox 差异确认 + 取消回退）/ `onHideSubTable` / `onRestoreSubTable` / `onJumpToReference` / `onCellChange` / `onAddDynamicRow` / `onRemoveDynamicRow` / `onSyncToDisclosureNotes` / `onContextChange` / `visibleSubTables` / `hiddenVisibleSubTables` / `visibleColumns` / `subClassBadges` 等 computed
- **emit 透传**：5 个（subtable-toggle / standard-switch / sync-to-disclosure-notes / jump-to-reference / save）

---

## 二、GtEControlTest 拆分详细设计

### 2.1 GtEControlTest.types.ts（需求 8）

从原文件 ~388-527 行剪切 13 个 interface。`EControlTestSchema` / `EControlTestData` / `SuggestionPayload` 保持 `export`（测试文件直接 import）。其余（FieldDef/SegmentDef/NextLogic/StepDef/HintItem/HintBlock/ConclusionOption/ConclusionBlock/DynamicTableColumnDef/DynamicTableSchema/SummaryRow）也全部 export 供子模式 SFC 共享。

```ts
export interface FieldDef { name: string; label: string; type?: ...; conditional?: string; ... }
export interface SegmentDef { id: string; title: string; fields?: FieldDef[]; ... }
export interface NextLogic { when?: string; goto?: number; ... }
export interface StepDef { step: number; id: string; title?: string; fields: FieldDef[]; next_logic?: NextLogic[]; is_terminal?: boolean; ... }
export interface HintItem { no: number; content: string }
export interface HintBlock { id: string; label: string; rows?: ...; ... }
export interface ConclusionOption { value: string; label: string; ... }
export interface ConclusionBlock { mode?: 'single' | 'per_row'; options?: ConclusionOption[]; ... }
export interface DynamicTableColumnDef { field: string; label: string; ... }
export interface DynamicTableSchema { start_row?: number; end_row?: number | string; columns?: ...; ... }
export interface EControlTestSchema { test_type?: 'summary'|'single'|'evaluation_step'; ... }
export interface SummaryRow { id?: string; conclusion?: string; [k: string]: any }
export interface EControlTestData { rows?: SummaryRow[]; fields?: ...; steps?: ...; conclusion?: string; active_step?: number; ... }
export interface SuggestionPayload { wp_id: string; sheet_name: string; conclusion: string; suggestion_type: ...; confidence: ...; source: string }
```

### 2.2 共用逻辑放置（safeEvaluate / FieldInput）

三个子模式都用到字段渲染和条件求值。**已 grep 实测确认**（2026-05-30）：

- `safeEvaluate`（条件表达式求值，原 675-722）→ 抽到 `econtrol/econtrolHelpers.ts`（纯函数，3 子模式 + shell 共用）
- `FieldInput`：是文件内**内联 defineComponent**（原 770 行起，解决 `<component :is>` 无法注入 `<el-option>` 子节点的限制），被 single（template 192）和 eval（template 262）两个子模式 template 使用 → **抽为独立 `econtrol/FieldInput.vue`**，single/eval 子组件各自 import
- `renderFieldInput`（原 748-764）是**死代码**（被 `void renderFieldInput` 标记、template 未用、注释写"Kept for backward compatibility"）→ **拆分时直接删除**（符合"死代码立即删除"铁律，不搬运）
- `stepLabel` / `stepShortTitle` / `hintTableRows` 等纯展示 helper → econtrolHelpers.ts

### 2.3 EControlSummaryTable.vue（需求 9）

```ts
const props = defineProps<{
  schema: EControlTestSchema
  rows: SummaryRow[]            // htmlData.rows，v-model 风格或 emit 回写
  readonly?: boolean
}>()
const emit = defineEmits<{
  'field-change': [row: SummaryRow, field: string, index: number]
  'add-row': []
  'remove-row': [index: number]
}>()
```

- 渲染 `summaryColumns`（computed 自 schema.dynamic_table）+ 各列类型（enum/multi_enum/number/text）
- `summaryRowClass`（按 deficiency 着色：重大缺陷红 / 控制缺陷黄）移入本组件
- 增删行 / 字段变更 emit 给 shell → debounceSave

### 2.4 EControlSingleForm.vue（需求 10）

```ts
const props = defineProps<{
  schema: EControlTestSchema
  data: Record<string, any>     // singleData
  readonly?: boolean
}>()
const emit = defineEmits<{
  'field-change': [name: string]
  'ai-suggest': [fieldName: string]
}>()
```

- 渲染 `segments`（computed）+ `visibleSegmentFields`（用 safeEvaluate 过滤 conditional）
- AI 建议入口透传给 shell 的 EControlAiPanel（见 2.7）
- 字段变更 emit `field-change` → shell debounceSave

### 2.5 EControlEvalStepper.vue（需求 11）

```ts
const props = defineProps<{
  schema: EControlTestSchema
  data: Record<string, any>     // evalData
  activeStepNo: number
  readonly?: boolean
}>()
const emit = defineEmits<{
  'field-change': [name: string]
  'step-advance': [step: number]
  'go-to-step': [index: number]
  'open-attachment': [rowRef: string]
}>()
```

- el-steps stepper + 当前步骤表单 + 上一步/下一步导航
- `steps` / `currentStep` / `activeStepIdx` / `stepProcessStatus` / `isTerminalStep` computed
- `evaluateNextLogic` / `advanceStep` / `goToStep` / `visibleStepFields` 逻辑
- **关键暴露**：测试 `vm.activeStepNo` / `vm.currentStep` / `vm.advanceStep` / `vm.goToStep` / `vm.isTerminalStep` 全部访问 → 这些必须在 **shell 顶层**暴露（见 2.8），故 `activeStepNo` ref 留 shell、`advanceStep`/`goToStep` 由 shell 持有并下传，或子组件 emit + shell 响应。设计采用：**activeStepNo ref 留 shell**，子组件通过 props 接收 + emit `step-advance`/`go-to-step` 通知 shell 改值；`currentStep`/`isTerminalStep` 在 shell computed（依赖 activeStepNo + schema）；`advanceStep`/`goToStep` 留 shell

### 2.6 useEControlConclusion.ts（需求 12）

```ts
export function useEControlConclusion(opts: {
  props: { wpId: string; sheetName: string }
  testType: Ref<string>
  conclusionValue: Ref<string>
  schema: Ref<EControlTestSchema>
  emit: (e: 'conclusion-change' | 'trigger-procedure-trimming-suggestion', payload: any) => void
}) {
  const conclusionBlock = computed(() => schema.value.conclusion ?? null)
  const conclusionOptions = computed(() => conclusionBlock.value?.options ?? [])  // 测试 vm.conclusionOptions 访问
  function deriveSuggestion(conclusion: string): SuggestionPayload['suggestion_type'] { /* 原 963-975 */ }
  function deriveConfidence(conclusion: string): SuggestionPayload['confidence'] { /* 原 976-982 */ }
  function onConclusionChange(value): void { /* 原 983+：emit conclusion-change + trigger-procedure-trimming-suggestion */ }
  return { conclusionBlock, conclusionOptions, deriveSuggestion, deriveConfidence, onConclusionChange }
}
```

- **关键暴露**：测试 `vm.conclusionOptions` / `vm.onConclusionChange` 直接访问 → shell 顶层解构

### 2.7 EControlAiPanel.vue（需求 12）

封装 `useWpAiSuggest` 接入 + 采纳/修改/忽略 UI，3 子模式复用。

```ts
const props = defineProps<{ wpId: string; sheetName: string; testType: string }>()
// 内部 const { aiEnabled, aiLoading, currentSuggestion, showSuggestionPanel, ... } = useWpAiSuggest(...)
// 暴露 requestSuggestion 给父/子模式触发，或子模式 emit 'ai-suggest' 冒泡到 shell 调用本面板
```

- 设计：AI 面板由 shell 持有（`useWpAiSuggest` 在 shell 或本组件实例化一次），子模式通过 emit `ai-suggest` 冒泡 → shell 转发给面板。保持原"单一 useWpAiSuggest 实例"行为。

### 2.8 GtEControlTest.vue shell（需求 12）

shell 保留：
- **template**：header + `v-if testType==='summary'` `<EControlSummaryTable>` / `v-else-if 'evaluation_step'` `<EControlEvalStepper>` / `v-else` `<EControlSingleForm>` + `<EControlAiPanel>` + 结论区 + 风险提示折叠
- **refs**（顶层，测试访问）：`summaryRows` / `singleData` / `evalData` / `activeStepNo` / `conclusionValue` / `activeHintIds`
- **computed 顶层**（测试访问）：`testType` / `currentStep` / `isTerminalStep` / `conclusionOptions`(来自 composable 解构)
- **composable 解构**：`useEControlConclusion`（暴露 conclusionOptions / onConclusionChange）
- **shell 保留函数**（测试访问）：`advanceStep` / `goToStep` / `onConclusionChange`(解构) / `initData` / `safeEvaluate`(或 helper)
- **emit 透传**：5 个（step-advance / conclusion-change / trigger-procedure-trimming-suggestion / save / open-attachment）

> ⚠ 设计权衡：EControlEvalStepper 的步骤状态（activeStepNo/advanceStep/goToStep）测试在 **vm 顶层**访问，故**不能**完全下沉到子组件。方案 = 状态机留 shell，子组件纯渲染 + emit；shell 顶层保留 `activeStepNo` ref + `advanceStep`/`goToStep` 函数 + `currentStep`/`isTerminalStep` computed，下传给 EControlEvalStepper 渲染。这样测试零改动。

---

## 三、关键设计决策（ADR 摘要）

| # | 决策 | 理由 | 备选（否决） |
|---|------|------|------|
| D1 | 状态 ref 全留 shell，composable 接收 ref 入参 | 单一数据源；测试 `vm.xxx` 访问点不破 | composable 内部持有状态副本（会导致 vm 访问 undefined） |
| D2 | composable 返回值必须 shell 顶层同名解构 | `<script setup>` 顶层绑定经 @vue/test-utils 的 **setupState 代理**暴露给 `wrapper.vm`（仅测试环境，**无需 defineExpose**；生产仍封闭），测试零改动 | 包在对象里 / 不解构 / 放嵌套作用域（vm.xxx 取不到 → 测试红） |
| D3 | 子组件只渲染 + emit，不持有 saveTimer / 不发 API | 副作用集中 shell，避免多处 timer 泄漏 | 子组件自管保存（行为分散难追） |
| D4 | EControl 步骤状态机留 shell（非下沉子组件） | 测试 vm.activeStepNo/advanceStep/goToStep 顶层访问 | 下沉 stepper（测试全红） |
| D5 | CNoteCell 保持 render function（h）形态 | 零行为差异、轻量；原本就是函数式 | 改写为 template（可能引入渲染差异） |
| D6 | 新建 cnote/ econtrol/ 子目录 | 避免 workpaper/ 根目录文件爆炸 | 平铺（根目录 +10 文件） |
| D7 | 纯函数抽 cnoteHelpers.ts / econtrolHelpers.ts | isLabelField/escapeNumber/safeEvaluate 等多处共用 | 各文件重复定义（漂移风险） |

## 四、测试策略

### 4.1 现有测试守护（不改断言）

- `GtCNoteTable.spec.ts` / `GtEControlTest.spec.ts` 全程绿
- 允许的改动：①import 路径（组件移到子目录）②`global.stubs` 增加新子组件 stub（若测试断言 DOM 不依赖子组件内部）
- **不允许**：改 `expect(...)` 断言、改 `vm.xxx` 访问名
- vm 访问清单（需求 13）逐项验证：每抽一个 composable 后立即跑对应 describe 块

### 4.2 新增单测（需求 13 AC-4）

| 测试文件 | 覆盖 | 用例数 |
|---------|------|-------|
| `CNoteCell.spec.ts` | 8 渲染分支各 1 + amount precision + readonly | ≥ 8 |
| `useCNoteFormula.spec.ts` | cellComputedValue（amount_formula/percent_formula）+ footerTotal | ≥ 5 |
| `useCNoteInheritance.spec.ts` | ok/mismatch/warning/na 4 态 + applicable_when 过滤 | ≥ 5 |
| `useEControlConclusion.spec.ts` | deriveSuggestion 4 结论 + deriveConfidence + onConclusionChange emit | ≥ 5 |

### 4.3 集成 / e2e

- vue-tsc --noEmit 0 error
- Playwright `test_c_class_renders_html` / `test_e_class_renders_html` 通过
- 真实 schema 抽样渲染目视（C-D2-disclosure / E-C12 / E-C12-1 / E-C11-2）

## 五、实施顺序（对应需求 14，每步一 commit）

**阶段 A — GtCNoteTable（C 与 E 不交叉）**
1. `GtCNoteTable.types.ts` + `cnote/cnoteHelpers.ts` → 原文件 import，跑测试绿
2. `useCNoteFormula.ts` + 单测 → shell 顶层解构，跑测试绿
3. `useCNoteInheritance.ts` + 单测 → shell 解构 ruleStatuses，跑 inheritance describe 绿
4. `useCNotePersist.ts` → shell 解构 initData/debounceSave，跑 save describe 绿
5. `CNoteCell.vue` + 单测 → shell template 引用，跑测试绿
6. `CNoteInheritanceBadge.vue` → shell 引用，跑测试绿
7. `CNoteSubTableCard.vue` → shell 遍历引用，跑测试绿
8. shell 精简至 ≤450 + 清死代码 → 跑全部 C 测试 + vue-tsc + Playwright C

**阶段 B — GtEControlTest（A 完成验证后才开始）**
9. `GtEControlTest.types.ts` + `econtrol/econtrolHelpers.ts` → 跑测试绿
10. `useEControlConclusion.ts` + 单测 → shell 解构 conclusionOptions/onConclusionChange，跑结论 describe 绿
11. `EControlAiPanel.vue` → shell 引用，跑测试绿
12. `EControlSummaryTable.vue` → shell v-if 引用，跑 summary 测试绿
13. `EControlSingleForm.vue` → shell v-else 引用，跑 single 测试绿
14. `EControlEvalStepper.vue`（状态机留 shell）→ 跑 stepper 测试绿（重点验证 vm.activeStepNo/advanceStep/goToStep）
15. shell 精简至 ≤350 + 清死代码 → 跑全部 E 测试 + vue-tsc + Playwright E

**阶段 C — 收尾**
16. 更新 `file_size_whitelist.txt`（移除 GtCNoteTable 1802）
17. 全量回归：两组件全部 vitest + vue-tsc + Playwright C/E + 真实 schema 目视

## 六、风险与缓解

| 风险 | 缓解 |
|------|------|
| 抽 composable 后 vm.xxx 变 undefined → 测试红 | D2 顶层同名解构 + 需求 13 清单逐项核对；每步即跑测试 |
| EControl 步骤状态下沉导致测试红 | D4 状态机留 shell（已在 2.5/2.8 定方案）|
| CNoteCell render function 搬运遗漏分支 | 8 分支清单（需求 2）+ CNoteCell.spec.ts 8 用例守护 |
| 子目录移动导致 import 路径漏改 | vue-tsc 全量编译兜底 + 每步跑测试 |
| 拆分中途行数仍超标 | 子组件预算留余量（≤450）；若某子组件仍超，二次拆（如 CNoteSubTableCard 再分 static/dynamic）|

> ✅ 原"FieldInput 是否独立未确认"风险已消除（2026-05-30 grep 实测）：FieldInput 是内联 defineComponent，抽为 `econtrol/FieldInput.vue`；renderFieldInput 是死代码直接删。

## 七、对外契约不变性保证（验收红线）

拆分前后以下**逐字节不变**：
- `htmlRendererRegistry.ts` 注册项（componentType `c-note-table` / `e-control-test` + component 指向 shell）
- 两 shell 的 props（各 5）+ emit（各 5）签名
- 保存 payload 结构（`CNoteTableHtmlData` / `EControlTestData`）
- `EControlTestSchema` / `EControlTestData` / `SuggestionPayload` 的 export（测试 import 依赖）
