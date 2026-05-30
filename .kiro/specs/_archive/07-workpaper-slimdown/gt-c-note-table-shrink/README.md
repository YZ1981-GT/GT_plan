# gt-c-note-table-shrink — HTML 渲染器超级 SFC 拆分

> 起草日期：2026-05-28
> 触发：底稿模块复盘（V3 spec gaps.md §B + memory.md 超级 SFC 风险铁律）
> 工时：2-3 工作日
> 优先级：**P2**（触碰时做）
> 状态：**未启动**（2026-05-30 代码实证复核，拆分 0 实施）

## ⚠ 2026-05-30 代码实证复核（重要：原 README 内容描述不准）

逐项 readCode + grep 核查后发现**原 README 多处与实际代码不符**，已据实修正：

| 原 README 说法 | 实际代码 | 证据 |
|---|---|---|
| GtCNoteTable 1608 行 | **~1802 行** | readFile 末尾 1620+ 仍 CSS 未结束 |
| GtEControlTest 1125 行 | **~1414 行** | readFile 末尾 `</style>` 在 1414 |
| GtCNoteTable = "合并/展开/批注/穿透/表头多级" | **无"批注"、无"多级表头"功能**；真实核心是上市/国企版本切换 + 子表折叠 + 子表↔主表联动校验 | 文件头 design §3.5 注释 + grep（comment/colspan/rowspan 0 命中） |
| GtEControlTest = 单一"6 步骤决策树" | **3 种结构路由**（summary 15列动态表 / single 7segments / evaluation_step 6步骤+4结论），6 步骤只是其中 1 个子模式 | 文件头 design §3.7 注释 |
| 拆分子组件 `CNoteTableHeader`（多级表头）/ `CNoteTableComments`（批注） | 实际无对应功能，命名张冠李戴 | grep 无 header-group / comment |

**结论**：原拆分方案基于错误的内容认知，**作废**。需按真实结构重新设计（见下）。

## 文件实际内容（readCode/grep 实证，2026-05-30）

### A. GtCNoteTable.vue（~1802 行，C 类附注披露嵌套表，design §3.5）

真实职责：
- 子表（4-7 张）可折叠卡片 + "不适用"软标记（`hidden_subtables` + `subtable-toggle`）
- **上市/国企版本切换**（standard switcher，listed↔soe，差异字段 ElMessageBox 提示）—— 核心功能
- 子表合计 ↔ 主表行实时联动校验（`inheritance_rules`，badge ✓/✗ + 差异）
- `applicable_to_sub_class` 按 standard 过滤子表/列
- static_rows / dynamic_rows 两种子表类型
- 7 种 render hints（amount / amount_formula / percent / percent_formula / checkmark / tag / index_chip）
- footer_total 自动 SUM
- cross_refs auto_pull 来源显示 + `jump-to-reference` 跳转（即原"穿透"）
- Debounced auto-save (1.5s) + `sync-to-disclosure-notes` 单向推送

### B. GtEControlTest.vue（~1414 行，C 类控制测试，design §3.7）

真实职责 = **3 种 test_type 结构路由**：
- `summary`：dynamic_table 15 列 + 提示折叠 + per_row 缺陷派生
- `single`：7 segments 顺序渲染 + 单一结论
- `evaluation_step`：el-steps 6 步骤 stepper + 4 互斥结论 radio
- 控制有效结论 → emit `trigger-procedure-trimming-suggestion`（联动 ProcedureTrimming）
- AI 建议面板（per field）+ 风险说明长段折叠

### C. GtAProgramConsole.vue（~629 行，OK 边缘，本 spec 不动）

## 重新设计的拆分方案（基于真实 script function 分组，2026-05-30 readCode 实测）

> 实测发现：两组件的逻辑高度内聚（大量 function 共享 `subTableData` / `evalData` 等响应式状态），
> 纯按"子组件"拆会产生大量 props/emit 透传样板。**更优策略 = 组件拆分 + composable 抽离并行**：
> 无状态纯函数（公式计算 / 规则求值 / 字段过滤）抽 composable，有 UI 的部分拆子组件。

### A. GtCNoteTable.vue（~1803 行 → shell + 子组件 + composable）

真实 function 分组（readCode 实测）：

| 真实模块 | 代表 function | 拆分去向 | 估行 |
|---|---|---|---|
| shell + 标准切换 header | `onStandardSwitch` / `deriveSubClassFromStandard` / `deriveStandardFromSubClass` | `GtCNoteTable.vue`（shell）| ≤ 350 |
| 子表卡片渲染 | `staticRowsView` / `dynamicRowsView` / `visibleColumns` / `buildEmptyRow` / `onAddDynamicRow` / `onRemoveDynamicRow` | `CNoteSubTableCard.vue` | ≤ 450 |
| 公式计算（**原方案漏列**）| `cellComputedValue` / `footerTotalColumns` / `footerTotalValue` | `useCNoteFormula.ts`（composable，纯函数）| ≤ 250 |
| inheritance 联动校验（最大块 7 函数）| `evaluateRule` / `computeRuleSource` / `computeRuleTarget` / `filterRows` / `ruleStatusForSubTable` / `ruleStatusTagType` / `ruleStatusIcon` | `useCNoteInheritance.ts`（composable）+ `CNoteInheritanceBadge.vue`（UI）| ≤ 350 |
| 子表"不适用"软标记 | `onHideSubTable` / `onRestoreSubTable` | shell 内保留（仅 2 函数，不独立）| — |
| 跨引用跳转 | `onJumpToReference` | shell 内保留（1 函数 emit）| — |
| init / save | `initData` / `buildSavePayload` / `debounceSave` | `useCNotePersist.ts`（composable）| ≤ 200 |

合计 shell ≤ 350 + 2 子组件 + 3 composable，**单文件 ≤ 450**。
（修正：原方案的 `CNoteStandardSwitcher`/`CNoteSubTableToggle`/`CNoteCrossRefJump` 实测都只有 1-3 个函数，独立成 SFC 反而增加透传样板，改为 shell 内保留 / composable 抽离。）

### B. GtEControlTest.vue（~1414 行 → shell + 3 子模式 SFC）

真实 function 分组（readCode 实测）— 3 子模式天然适合拆 SFC：

| 真实模块 | 代表 function/computed | 拆分去向 | 估行 |
|---|---|---|---|
| shell + test_type 路由 | `testType` computed + `initData` + `safeEvaluate` / `renderFieldInput` 共用 | `GtEControlTest.vue`（shell）| ≤ 250 |
| summary 子模式 | `summaryColumns` / `summaryRowClass` / `buildEmptySummaryRow` / `handleAddSummaryRow` / `handleRemoveSummaryRow` / `onSummaryFieldChange` | `EControlSummaryTable.vue` | ≤ 320 |
| single 子模式 | `segments` / `visibleSegmentFields` / `onSingleFieldChange` | `EControlSingleForm.vue` | ≤ 280 |
| evaluation_step 子模式 | `steps` / `currentStep` / `activeStepIdx` / `evaluateNextLogic` / `advanceStep` / `goToStep` / `visibleStepFields` / `stepLabel` / `stepShortTitle` | `EControlEvalStepper.vue` | ≤ 350 |
| 结论 → ProcedureTrimming 建议 | `conclusionBlock` / `deriveSuggestion` / `deriveConfidence` / `onConclusionChange` | `useEControlConclusion.ts`（composable，3 模式共用）| ≤ 200 |
| AI 建议面板 | `onAiSuggestField` / `handleAdoptField` / `handleModifyField` / `handleIgnoreE`（已基于 `useWpAiSuggest`）| `EControlAiPanel.vue` | ≤ 180 |

合计 shell ≤ 250 + 3 子模式 SFC + AI 面板 + 1 composable，**单文件 ≤ 350**。

### C. GtAProgramConsole.vue（~629 行，OK 边缘，本 spec 不动）

### 真实 emit 契约（实测，拆分时 shell 必须透传）

- GtCNoteTable：`subtable-toggle` / `standard-switch` / `sync-to-disclosure-notes` / `jump-to-reference`
- GtEControlTest：`step-advance` / `conclusion-change` / `open-attachment` / `trigger-procedure-trimming-suggestion`（+ AI 相关）

## 不在范围

- 修改 cycle 业务逻辑（仅 SFC 结构拆分）
- 触碰 htmlRendererRegistry（registry 由 shell 统一注册）
- 改 backend service / DB / router

## 验收

- 子组件各自 ≤ 450 行（C）/ ≤ 350 行（E）
- 现有 vitest（GtCNoteTable / GtEControlTest 测试）全绿，0 回归
- vue-tsc 0 errors
- Playwright 现有 e2e 通过（含附注同步 / 控制测试 3 模式导航）

## Sprint 划分（2-3 天）

| Sprint | 工时 | 内容 |
|---|---|---|
| 0. 准备 | 0.5 天 | readCode 复核最新 function 分组 + 静态依赖图 + 现有测试基线 |
| 1. GtCNoteTable 拆 | 1 天 | shell + CNoteSubTableCard/CNoteInheritanceBadge 子组件 + useCNoteFormula/useCNoteInheritance/useCNotePersist 三 composable |
| 2. GtEControlTest 拆 3 模式 | 1 天 | shell + summary/single/eval 三子模式 SFC + EControlAiPanel + useEControlConclusion |
| 3. 测试 + CI 卡点 | 0.5 天 | 补子组件/composable vitest + 更新 file_size_whitelist baseline（移除 GtCNoteTable 1802 登记）|

## 启动判断

- 纯前端重构债，无外部依赖，**可随时启动**
- "触碰式重构"——README 自定原则「下次动该组件功能时顺手拆」，不单独立项除非阻塞新需求
- 下一步：启动时先 readCode 复核两文件最新结构（持续膨胀），再起完整三件套
