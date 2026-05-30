---
spec: gt-c-note-table-shrink
status: draft
version: v1.0
created: 2026-05-30
type: 前端重构（超级 SFC 拆分）
---

# 需求文档：GtCNoteTable / GtEControlTest 超级 SFC 拆分

## 引言

`GtCNoteTable.vue`（1803 行）和 `GtEControlTest.vue`（1414 行）是 HTML 底稿渲染器的两个核心组件，分别渲染 C 类附注披露嵌套表（166 sheet）和 E 类控制测试（322 sheet）。两者已在 `htmlRendererRegistry.ts` 注册、有完整 vitest + Playwright e2e 覆盖、由 render_schema yaml 驱动，是**高度活跃**的生产组件。

问题：`GtCNoteTable.vue`（1803 行）**已超**「前端单文件 ≤ 1500 行」卡点，且已在 `file_size_whitelist.txt` 登记 1802 grandfather（硬性必拆）；`GtEControlTest.vue`（1414 行）**逼近但未超** 1500 阈值（未登记 whitelist），属预防性拆分——但其 `summary` / `single` / `evaluation_step` 三子模式职责天然可分，拆分收益明确。两者逻辑高度集中导致：任何附注子表/控制测试步骤的小改动都要在 1400-1800 行文件里操作，回归风险高、code review 困难。

本 spec 目标：**纯结构拆分，零功能损失、零行为改变**。把两个超级 SFC 拆为 shell + 子组件 + composable，每个产物文件可控（≤ 450 行）。

### 核心约束（贯穿全部需求）

1. **零功能损失**：拆分前后 UI 渲染、交互、emit 事件、保存数据结构完全一致
2. **零接口变更**：对父组件（`htmlRendererRegistry` / `GtWpRenderer`）的 props / emit 契约不变
3. **测试守护**：现有 vitest（GtCNoteTable.spec.ts / GtEControlTest.spec.ts）+ Playwright e2e 全程绿，不允许为「适配拆分」而改测试断言
4. **仅前端**：不碰 backend service / DB / router / render_schema yaml

### 实测接口契约（拆分时 shell 必须原样保持）

**GtCNoteTable**
- props：`wpId` / `sheetName` / `schema: CNoteTableSchema` / `htmlData: CNoteTableHtmlData` / `readonly`
- emit：`subtable-toggle` / `standard-switch` / `sync-to-disclosure-notes` / `jump-to-reference` / `save`

**GtEControlTest**
- props：`wpId` / `sheetName` / `schema: EControlTestSchema` / `htmlData: EControlTestData` / `readonly`
- emit：`step-advance` / `conclusion-change` / `trigger-procedure-trimming-suggestion` / `save` / `open-attachment`

---

## 需求 1：抽离共享类型定义

**用户故事**：作为维护者，我希望 GtCNoteTable 的 15 个 interface 类型抽到独立 types 文件，以便 shell 和各子组件/composable 共享同一套类型，避免重复声明。

#### 验收标准

1. WHEN 拆分开始 THEN 系统 SHALL 新建 `GtCNoteTable.types.ts`，包含全部实测类型：`SubTableType` / `ColumnType` / `RenderHint` / `SubClass` / `ColumnDef` / `ColumnDefWithKey` / `StaticRowDef` / `FooterTotalDef` / `SubTableSchema` / `InheritanceRuleSourceTarget` / `InheritanceRule` / `VersionVariant` / `ContextField` / `CrossRefDef` / `LinkageDownstreamRule` / `LinkageDef` / `CNoteTableSchema` / `RowData` / `CNoteTableHtmlData` / `SyncPayload` / `RuleStatus`
2. WHEN 类型抽离后 THEN shell + 子组件 + composable SHALL 全部从该文件 import，不得重复定义
3. WHEN vue-tsc 编译 THEN 系统 SHALL 0 type error（类型签名与原文件逐字一致）

## 需求 2：CNoteCell 单元格渲染器独立成子组件

**用户故事**：作为维护者，我希望文件内 `defineComponent` 定义的 `CNoteCell`（156 行渲染逻辑）抽为独立 `.vue`，以便单元格渲染逻辑可独立测试和复用。

#### 验收标准

1. WHEN 拆分 THEN 系统 SHALL 新建 `CNoteCell.vue`，保留全部 8 种渲染分支：readonly/label 只读、`amount_formula`、`percent_formula`、`boolean` checkbox、`number`（含 amount precision=2）、`enum`、`multi_enum`、`date`、`textarea`、默认 text
2. WHEN CNoteCell 渲染 THEN props SHALL 为 `row` / `col` / `readonly` / `computedValue`，emit SHALL 为 `change`（与原内联组件逐一致）
3. WHEN 单元格依赖 `isLabelField` / `formatPercent` / `formatAmount` THEN 这些 helper SHALL 由 CNoteCell 自身 import（`formatAmount` 来自 `@/utils/formatAmount`，`isLabelField` / `formatPercent` 迁入共享 util 或组件内联）
4. WHEN amount 类型 THEN SHALL 保持 `gt-amt` class + `controlsPosition: 'right'` + `precision: 2`（金额显示铁律不破坏）

## 需求 3：子表卡片渲染拆为子组件

**用户故事**：作为维护者，我希望单张子表的渲染（static_rows 表格 / dynamic_rows 表格 + 工具栏 + 合计行）抽为 `CNoteSubTableCard.vue`，让 shell 只负责遍历子表列表。

#### 验收标准

1. WHEN 拆分 THEN 系统 SHALL 新建 `CNoteSubTableCard.vue`，渲染单张 `SubTableSchema`：static_rows（el-table + CNoteCell）/ dynamic_rows（新增行按钮 + el-table + 删除列 + footer_total 合计行）
2. WHEN dynamic_rows 子表 THEN SHALL 保留「新增行」按钮 disabled 逻辑（`reachedMaxRows`）+ 行数 badge（`当前 / max_rows`）+ 删除行操作列
3. WHEN 子表有 footer_total.enabled THEN SHALL 渲染底部合计行（`footerTotalColumns` + `footerTotalValue` + `gt-amt` 格式）
4. WHEN 单元格变更 / 增删行 THEN SHALL 通过 emit 通知父级触发 debounce save，不在子组件内直接持有 saveTimer
5. WHEN 子组件渲染列 THEN SHALL 调用注入的 `cellComputedValue`（公式计算）+ `visibleColumns`（standard 过滤）逻辑，保持与原行为一致

## 需求 4：公式计算逻辑抽为 composable

**用户故事**：作为维护者，我希望单元格公式计算（`cellComputedValue` / `footerTotalColumns` / `footerTotalValue`）这组纯逻辑抽为 `useCNoteFormula.ts`，以便公式逻辑可独立单测、不与 UI 耦合。

#### 验收标准

1. WHEN 拆分 THEN 系统 SHALL 新建 `useCNoteFormula.ts`，导出 `cellComputedValue` / `footerTotalColumns` / `footerTotalValue` 三个函数
2. WHEN 公式计算 THEN SHALL 保持原 amount_formula / percent_formula 求值逻辑逐字一致（含 `escapeNumber` 数值转换）
3. WHEN composable 被调用 THEN SHALL 接收 `subTableData` 响应式引用作为入参，不在 composable 内持有组件状态副本

## 需求 5：inheritance_rules 联动校验抽为 composable + badge 子组件

**用户故事**：作为维护者，我希望子表↔主表合计联动校验（7 个函数中最大的逻辑块）拆为 `useCNoteInheritance.ts`（求值逻辑）+ `CNoteInheritanceBadge.vue`（徽标 UI），让校验逻辑可独立测试。

#### 验收标准

1. WHEN 拆分 THEN 系统 SHALL 新建 `useCNoteInheritance.ts`，导出 `evaluateRule` / `computeRuleSource` / `computeRuleTarget` / `filterRows` + `ruleStatuses` computed
2. WHEN 拆分 THEN 系统 SHALL 新建 `CNoteInheritanceBadge.vue`，渲染 `ruleStatusForSubTable` 结果（el-tooltip + el-tag + `ruleStatusTagType` 颜色 + `ruleStatusIcon` 图标）
3. WHEN 校验状态 THEN SHALL 保留 4 态：`ok`（绿✓）/ `mismatch`（红✗）/ `warning`（黄）/ `na`，含 diff 差异金额 tooltip
4. WHEN inheritance_rules 含 `applicable_when.standard` THEN SHALL 按当前 standard 过滤规则（与原行为一致）

## 需求 6：数据初始化与持久化抽为 composable

**用户故事**：作为维护者，我希望数据装载/保存（`initData` / `buildSavePayload` / `debounceSave`）抽为 `useCNotePersist.ts`，统一管理 saveTimer 与 save emit。

#### 验收标准

1. WHEN 拆分 THEN 系统 SHALL 新建 `useCNotePersist.ts`，导出 `initData` / `buildSavePayload` / `debounceSave`
2. WHEN debounceSave 触发 THEN SHALL 保持 1.5s 防抖 + readonly 短路 + emit `save` payload（结构与原 `CNoteTableHtmlData` 一致）
3. WHEN 组件卸载 THEN SHALL 在 `onBeforeUnmount` 清理 saveTimer（不泄漏 timer）
4. WHEN initData 装载 THEN SHALL 保持从 `htmlData` 还原 sub_table_data / hidden_subtables / current_standard / context 的逻辑

## 需求 7：GtCNoteTable shell 精简

**用户故事**：作为维护者，我希望 GtCNoteTable.vue 退化为 shell（≤ 450 行），仅负责 header + standard switcher + context 表单 + 子表列表遍历 + 引用来源 + 同步按钮，业务逻辑委托子组件/composable。

#### 验收标准

1. WHEN 拆分完成 THEN `GtCNoteTable.vue` SHALL ≤ 450 行，且保留全部 5 个 emit 透传
2. WHEN shell 保留 THEN SHALL 含：header（实体/期间/章节/索引号 + standard switcher el-radio-group）+ context 字段表单 + 隐藏子表恢复区 + 子表 el-collapse 遍历 + cross_refs 来源区 + 同步附注 footer
3. WHEN standard 切换 THEN SHALL 保留 `onStandardSwitch` 的 ElMessageBox 差异确认 + 取消回退逻辑（shell 内保留，仅 3 函数）
4. WHEN 「不适用」软标记 / cross-ref 跳转 THEN `onHideSubTable` / `onRestoreSubTable` / `onJumpToReference` SHALL 在 shell 内保留（各 1-2 函数，不独立）
5. WHEN 拆分后 THEN `file_size_whitelist.txt` SHALL 移除 GtCNoteTable 1802 登记（不再需要 grandfather）

---

## 需求 8：GtEControlTest 共享类型抽离

**用户故事**：作为维护者，我希望 GtEControlTest 的 13 个类型抽到 `GtEControlTest.types.ts`，供 shell 和 3 个子模式 SFC 共享。

#### 验收标准

1. WHEN 拆分 THEN 系统 SHALL 新建 `GtEControlTest.types.ts`，含全部 13 个实测 interface：`FieldDef` / `SegmentDef` / `NextLogic` / `StepDef` / `HintItem` / `HintBlock` / `ConclusionOption` / `ConclusionBlock` / `DynamicTableColumnDef` / `DynamicTableSchema` / `EControlTestSchema` / `SummaryRow` / `EControlTestData` / `SuggestionPayload`（保持 `export` 的 `EControlTestSchema` / `EControlTestData` / `SuggestionPayload` 对外可见，因测试文件 import 它们）
2. WHEN vue-tsc 编译 THEN SHALL 0 type error，且 `GtEControlTest.spec.ts` 对 `EControlTestSchema` 的 import 不受影响
3. WHEN 类型抽离 THEN shell + 3 子模式 SFC SHALL 共享同一套类型

## 需求 9：summary 子模式拆为子组件

**用户故事**：作为维护者，我希望 `test_type === 'summary'` 分支（动态表 15 列 + per_row 缺陷派生）拆为 `EControlSummaryTable.vue`。

#### 验收标准

1. WHEN 拆分 THEN 系统 SHALL 新建 `EControlSummaryTable.vue`，含 `summaryColumns` 渲染（enum/multi_enum/number/text 各列类型）+ 新增控制行 + 删除行 + `summaryRowClass`（重大缺陷红 / 控制缺陷黄）
2. WHEN summary 行变更 THEN SHALL emit 通知父级 debounce save（`onSummaryFieldChange` 行为不变）
3. WHEN per_row 缺陷派生 THEN SHALL 保持 `summaryRowClass` 按 `deficiency` 字段着色逻辑一致

## 需求 10：single 子模式拆为子组件

**用户故事**：作为维护者，我希望 `test_type === 'single'` 分支（7 segments 顺序渲染 + 单一结论）拆为 `EControlSingleForm.vue`。

#### 验收标准

1. WHEN 拆分 THEN 系统 SHALL 新建 `EControlSingleForm.vue`，含 `segments` 遍历渲染 + `visibleSegmentFields`（conditional 字段过滤）+ AI 建议入口
2. WHEN single 字段变更 THEN SHALL 保持 `onSingleFieldChange` → debounce save 行为
3. WHEN segment 含 conditional 字段 THEN SHALL 用 `safeEvaluate` 求值决定显隐（逻辑不变）

## 需求 11：evaluation_step 子模式拆为子组件

**用户故事**：作为维护者，我希望 `test_type === 'evaluation_step'` 分支（el-steps 6 步骤 stepper + 4 互斥结论）拆为 `EControlEvalStepper.vue`。

#### 验收标准

1. WHEN 拆分 THEN 系统 SHALL 新建 `EControlEvalStepper.vue`，含 el-steps stepper + 当前步骤表单 + 步骤导航（上一步/下一步）+ `evaluateNextLogic` 条件跳转
2. WHEN 步骤推进 THEN SHALL 保持 `advanceStep` / `goToStep` 逻辑 + emit `step-advance` + `visibleStepFields` 条件字段过滤
3. WHEN 终态步骤（is_terminal）THEN SHALL 保持 `stepProcessStatus` 状态机 + final_conclusion 字段同步到 conclusionValue
4. WHEN 步骤含附件入口 THEN SHALL 保留 emit `open-attachment`

## 需求 12：结论联动 + AI 面板抽离，shell 精简

**用户故事**：作为维护者，我希望结论→ProcedureTrimming 建议逻辑抽为 `useEControlConclusion.ts`（3 模式共用）、AI 建议面板抽为 `EControlAiPanel.vue`，GtEControlTest.vue 退化为 ≤ 350 行 shell（test_type 路由分发）。

#### 验收标准

1. WHEN 拆分 THEN 系统 SHALL 新建 `useEControlConclusion.ts`，导出 `deriveSuggestion` / `deriveConfidence` / `onConclusionChange`，保持 emit `conclusion-change` + `trigger-procedure-trimming-suggestion`（payload 结构 `SuggestionPayload` 不变）
2. WHEN 拆分 THEN 系统 SHALL 新建 `EControlAiPanel.vue`，封装 `useWpAiSuggest` 接入 + 采纳/修改/忽略建议（3 子模式复用同一面板）
3. WHEN 拆分完成 THEN `GtEControlTest.vue` SHALL ≤ 350 行，保留 header + test_type 路由分发（v-if summary / v-else-if evaluation_step / v-else single）+ 全部 5 个 emit 透传
4. WHEN 共用逻辑 THEN `safeEvaluate` / `renderFieldInput` / `initData` SHALL 在 shell 或共享 util 保留供 3 子模式调用

---

## 需求 13：测试守护与回归门禁（贯穿全程）

**用户故事**：作为质控，我要求拆分全程由现有测试守护，确保零功能损失可被证明。

#### 验收标准

1. WHEN 每个子组件/composable 拆出 THEN 现有 `GtCNoteTable.spec.ts` / `GtEControlTest.spec.ts` SHALL 全绿，**不允许修改断言**（仅允许调整 import 路径 + 必要的子组件 stub）
2. WHEN 拆分前 THEN SHALL 先 grep 两个 spec 测试中所有 `wrapper.vm.\w+` / `vm.\w+` 访问点，列为「shell 必须保持 setup 顶层暴露」清单，实施时逐项确认。**已 grep 实测的清单（拆分后必须仍可 `vm.` 访问）**：
   - GtCNoteTable：`currentStandardSubClass` / `visibleSubTables` / `contextData` / `ruleStatuses` / `hiddenSubtables` / `subTableData` / `schema` / `sectionId` / `onCellChange` / `onSyncToDisclosureNotes`
   - GtEControlTest：`activeStepNo` / `currentStep` / `evalData` / `isTerminalStep` / `conclusionOptions` / `advanceStep` / `goToStep` / `onConclusionChange`
3. WHEN 逻辑抽为 composable THEN shell SHALL 在 `<script setup>` **顶层同名解构** composable 返回值（如 `const { ruleStatuses } = useCNoteInheritance(...)`、`const { activeStepNo, currentStep, advanceStep, goToStep } = ...`），保证上述清单中的访问点不变为 undefined
4. WHEN 拆分完成 THEN SHALL 为新子组件/composable 补 vitest：CNoteCell（8 渲染分支）/ useCNoteFormula / useCNoteInheritance / useEControlConclusion 各 ≥ 5 用例
5. WHEN 拆分完成 THEN `vue-tsc --noEmit` SHALL 0 error
6. WHEN 拆分完成 THEN Playwright e2e（`test_c_class_renders_html` / `test_e_class_renders_html`）SHALL 通过
7. WHEN 拆分完成 THEN 用真实 render_schema yaml（C-D2-disclosure / E-C12 / E-C12-1 / E-C11-2）渲染抽样底稿，目视确认与拆分前一致

## 需求 14：增量拆分顺序与可回滚

**用户故事**：作为实施者，我要求按依赖顺序增量拆分，每步可独立验证、任一步失败可回滚，避免一次性大改导致功能损失难以定位。

#### 验收标准

1. WHEN 拆分 THEN SHALL 按依赖顺序：①types → ②纯逻辑 composable（useCNoteFormula / useCNoteInheritance / useCNotePersist / useEControlConclusion）→ ③叶子子组件（CNoteCell / CNoteInheritanceBadge / EControlAiPanel）→ ④容器子组件（CNoteSubTableCard / 3 个 EControl 子模式）→ ⑤shell 精简
2. WHEN 每抽出一个产物 THEN SHALL 立即跑对应 spec 测试，绿后才抽下一个；红则回滚该步重做
3. WHEN 单步改动 THEN SHALL 控制在一个 git commit 内（每个产物一次提交），便于二分定位回归
4. WHEN 一个组件全部拆完 THEN SHALL 跑 vue-tsc + 该组件全部 vitest + Playwright 验证后，才开始拆另一个组件（C 与 E 不交叉进行）

## 非功能需求

| 维度 | 要求 |
|------|------|
| 单文件行数 | shell ≤ 450（C）/ ≤ 350（E）；子组件 ≤ 450；composable ≤ 250 |
| 性能 | 拆分不引入额外渲染开销；CNoteCell 仍为轻量函数式渲染 |
| 命名 | 子组件 `CNote*` / `EControl*` 前缀；composable `useCNote*` / `useEControl*` |
| 注册 | htmlRendererRegistry 仍只注册 GtCNoteTable / GtEControlTest 两个 shell（子组件不进 registry）|
| 死代码 | 拆分后原内联 defineComponent / 函数不得残留在 shell |

## 范围边界

**做**：
- GtCNoteTable.vue（1803）拆 shell + CNoteCell + CNoteSubTableCard + CNoteInheritanceBadge + 3 composable + types
- GtEControlTest.vue（1414）拆 shell + 3 子模式 SFC + EControlAiPanel + 1 composable + types
- 补子组件/composable 单测 + 更新 file_size_whitelist 基线

**不做**：
- 修改任何 C/E 类业务逻辑、渲染规则、公式语义
- 改 render_schema yaml / backend / DB / router
- 拆 GtAProgramConsole.vue（629 行，OK 边缘，触碰时再议）
- 改 htmlRendererRegistry 注册结构 / GtWpRenderer 父组件契约

## 成功判据汇总

| # | 判据 | 验证方式 |
|---|------|---------|
| 1 | GtCNoteTable.vue ≤ 450 行 | wc -l |
| 2 | GtEControlTest.vue ≤ 350 行 | wc -l |
| 3 | 现有 2 个 spec 测试零断言改动全绿 | vitest |
| 4 | 所有 `vm.xxx` 测试访问点拆分后仍可访问（shell 顶层同名解构）| vitest + grep |
| 5 | 新子组件/composable 单测 ≥ 5 用例各 | vitest |
| 6 | vue-tsc 0 error | vue-tsc --noEmit |
| 7 | Playwright C/E 类渲染 e2e 通过 | playwright |
| 8 | 5 个 emit（各组件）契约不变 | grep defineEmits + 测试 |
| 9 | GtEControlTest.types.ts 含全 13 interface | grep + vue-tsc |
| 10 | file_size_whitelist 移除 GtCNoteTable | grep |
| 11 | 增量拆分每产物一 commit，可二分回滚 | git log |
