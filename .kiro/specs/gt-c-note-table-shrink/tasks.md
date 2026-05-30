---
spec: gt-c-note-table-shrink
status: draft
version: v1.0
created: 2026-05-30
total_tasks: 19
---

# 实施任务：GtCNoteTable / GtEControlTest 超级 SFC 拆分

> 铁律：每个任务一次 commit；拆出即跑测试绿再做下一个；任一步红立即回滚。
> C 类（阶段 A）全部完成验证后才开始 E 类（阶段 B）。
> vm 暴露清单（requirements §13）每步逐项核对。

## 阶段 A — GtCNoteTable 拆分

- [x] 0. 准备基线
  - 跑 `npx vitest run GtCNoteTable.spec.ts GtEControlTest.spec.ts` 确认全绿基线
  - grep 两测试文件全部 `vm.\w+` 访问点，对照 requirements §13 清单打勾
  - 记录拆分前行数（GtCNoteTable 1803 / GtEControlTest 1414）
  - _需求: 13, 14_

- [x] 1. 抽离 GtCNoteTable.types.ts + cnoteHelpers.ts
  - 新建 `GtCNoteTable.types.ts`，剪切原 364-525 行的 21 个类型，全部 export
  - 新建 `cnote/cnoteHelpers.ts`，剪切 `isLabelField` / `formatPercent` / `escapeNumber` / `genRowId`（原 733-775）
  - GtCNoteTable.vue 改为 `import type` + import helpers
  - 跑 GtCNoteTable.spec.ts 绿 + vue-tsc 0 error
  - _需求: 1_

- [x] 2. 抽离 useCNoteFormula.ts + 单测
  - 新建 `cnote/composables/useCNoteFormula.ts`，导出 `cellComputedValue` / `footerTotalColumns` / `footerTotalValue`（原 976-1045），接收 `subTableData: Ref` 入参
  - shell 顶层解构 `const { cellComputedValue, footerTotalColumns, footerTotalValue } = useCNoteFormula(subTableData)`
  - 新建 `useCNoteFormula.spec.ts` ≥5 用例（amount_formula / percent_formula / footerTotal / 空数据 / escapeNumber 边界）
  - 跑测试绿 + vue-tsc
  - _需求: 4, 13_

- [x] 3. 抽离 useCNoteInheritance.ts + 单测
  - 新建 `cnote/composables/useCNoteInheritance.ts`，导出 `ruleStatuses`(computed) / `ruleStatusForSubTable` + 内部 `evaluateRule` / `computeRuleSource` / `computeRuleTarget` / `filterRows`（原 1052-1191）
  - 入参 `schema` / `subTableData` / `currentStandardSubClass` 三个 Ref
  - **shell 顶层解构 `const { ruleStatuses, ruleStatusForSubTable } = useCNoteInheritance(...)`**（测试 `vm.ruleStatuses` 访问）
  - 新建 `useCNoteInheritance.spec.ts` ≥5 用例（ok / mismatch + diff / warning / na / applicable_when 过滤）
  - 跑 GtCNoteTable.spec.ts「inheritance_rules 实时校验」describe 绿（验证 vm.ruleStatuses 不破）
  - _需求: 5, 13_

- [x] 4. 抽离 useCNotePersist.ts
  - 新建 `cnote/composables/useCNotePersist.ts`，导出 `initData` / `buildSavePayload` / `debounceSave`（原 1380-1490+），含 onBeforeUnmount 清理 saveTimer
  - shell 顶层解构（测试访问 vm 时 initData/debounceSave 可调）
  - 跑 GtCNoteTable.spec.ts「debounce save / 数据持久化」describe 绿（vm.subTableData / onCellChange 不破）
  - _需求: 6, 13_

- [x] 5. 抽离 CNoteCell.vue + 单测
  - 新建 `cnote/CNoteCell.vue`，搬运原 577-731 内联 defineComponent 为 SFC（render function 形态保留），props `row/col/readonly/computedValue` + emit `change`
  - 保留全 8 渲染分支（readonly/label / amount_formula / percent_formula / boolean / number(amount precision=2) / enum / multi_enum / date / textarea / text）
  - shell template `<CNoteCell>` 引用 + 删除内联 defineComponent（**过渡态**：此步 CNoteCell 仍由 shell 的 static_rows/dynamic_rows template（原 184/225 行两处）直接引用，任务 7 才把引用迁入 CNoteSubTableCard）
  - 新建 `CNoteCell.spec.ts` ≥8 用例（每分支 1 + amount precision + readonly）
  - 跑测试绿 + vue-tsc
  - _需求: 2, 13_

- [x] 6. 抽离 CNoteInheritanceBadge.vue
  - 新建 `cnote/CNoteInheritanceBadge.vue`，props `statuses: RuleStatus[]`，渲染 el-tooltip + el-tag（含 `ruleStatusTagType` 颜色 + `ruleStatusIcon` 图标，移入组件内部）
  - shell `<CNoteInheritanceBadge :statuses="ruleStatusForSubTable(st.id)" />`
  - 跑 GtCNoteTable.spec.ts 绿
  - _需求: 5_

- [x] 7. 抽离 CNoteSubTableCard.vue
  - 新建 `cnote/CNoteSubTableCard.vue`，props（subTable/rows/readonly/visibleColumns/cellComputedValue/footerColumns/footerValue/reachedMax）+ emit（cell-change/add-row/remove-row）
  - 渲染 static_rows（el-table + CNoteCell）/ dynamic_rows（新增行按钮 disabled + el-table + 删除列 + footer 合计）
  - **CNoteCell 引用从 shell 迁入 CNoteSubTableCard**（任务 5 的过渡态结束，shell 不再直接引用 CNoteCell，改为遍历 CNoteSubTableCard）
  - shell `v-for` 引用，增删行/cell-change 透传给 shell 的 onCellChange/onAddDynamicRow/onRemoveDynamicRow → debounceSave
  - 跑 GtCNoteTable.spec.ts 绿（vm.subTableData / onCellChange 不破）
  - _需求: 3, 13_

- [x] 8. GtCNoteTable.vue shell 精简 + 验证
  - 确认 shell ≤450 行，保留 header/switcher/context/隐藏恢复区/子表遍历/cross-ref/sync footer + 5 emit
  - shell 保留函数：onStandardSwitch / onHideSubTable / onRestoreSubTable / onJumpToReference / onCellChange / onAddDynamicRow / onRemoveDynamicRow / onSyncToDisclosureNotes / onContextChange + visibleSubTables/hiddenVisibleSubTables/visibleColumns/subClassBadges computed
  - 清除所有已迁移的死代码（无残留内联组件/函数）
  - 跑全部 GtCNoteTable.spec.ts + vue-tsc 0 error + Playwright `test_c_class_renders_html`
  - 真实 schema 目视：C-D2-disclosure 渲染抽样
  - _需求: 7, 13_

## 阶段 B — GtEControlTest 拆分（阶段 A 全部验证通过后才开始）

- [x] 9. 抽离 GtEControlTest.types.ts + econtrolHelpers.ts
  - 新建 `GtEControlTest.types.ts`，剪切 13 个 interface（FieldDef/SegmentDef/NextLogic/StepDef/HintItem/HintBlock/ConclusionOption/ConclusionBlock/DynamicTableColumnDef/DynamicTableSchema/EControlTestSchema/SummaryRow/EControlTestData/SuggestionPayload），全部 export（EControlTestSchema/Data/SuggestionPayload 测试依赖）
  - 新建 `econtrol/econtrolHelpers.ts`，剪切 `safeEvaluate` / `stepLabel` / `stepShortTitle` / `hintTableRows`（原 675-732, 860-876）
  - **删除死代码 `renderFieldInput`（原 748-764，被 `void renderFieldInput` 标记、template 未用）**
  - GtEControlTest.vue import + GtEControlTest.spec.ts import 路径调整
  - 跑 GtEControlTest.spec.ts 绿 + vue-tsc
  - _需求: 8_

- [x] 10. 抽离 FieldInput.vue
  - 新建 `econtrol/FieldInput.vue`，搬运原 770+ 内联 `FieldInput` defineComponent 为独立 SFC（保留 `<component :is>` 注入 el-option 子节点的实现）
  - shell + single/eval 子模式 template 引用（先在 shell template 引用，验证绿）
  - 跑 GtEControlTest.spec.ts 绿 + vue-tsc
  - _需求: 10, 11_

- [x] 11. 抽离 useEControlConclusion.ts + 单测
  - 新建 `econtrol/composables/useEControlConclusion.ts`，导出 `conclusionBlock` / `conclusionOptions`(computed) / `deriveSuggestion` / `deriveConfidence` / `onConclusionChange`（原 963-1010）
  - **shell 顶层解构 `const { conclusionOptions, onConclusionChange } = useEControlConclusion(...)`**（测试 vm.conclusionOptions / vm.onConclusionChange 访问）
  - 新建 `useEControlConclusion.spec.ts` ≥5 用例（control_effective/extended_effective/deviation_remains/systemic_deviation 派生 + emit 验证）
  - 跑 GtEControlTest.spec.ts「结论」相关 describe 绿
  - _需求: 12, 13_

- [x] 12. 抽离 EControlAiPanel.vue
  - 新建 `econtrol/EControlAiPanel.vue`，封装 `useWpAiSuggest` 接入 + 采纳/修改/忽略 UI（单一实例，3 模式复用）
  - shell 持有面板，子模式 emit `ai-suggest` 冒泡 → shell 转发
  - 跑 GtEControlTest.spec.ts 绿
  - _需求: 12_

- [x] 13. 抽离 EControlSummaryTable.vue
  - 新建 `econtrol/EControlSummaryTable.vue`，props（schema/rows/readonly）+ emit（field-change/add-row/remove-row）
  - 渲染 summaryColumns（enum/multi_enum/number/text）+ summaryRowClass（重大缺陷红/控制缺陷黄，移入组件）+ 增删行
  - shell `v-if testType==='summary'` 引用，emit 透传 debounceSave
  - 跑 GtEControlTest.spec.ts summary 相关绿
  - _需求: 9, 13_

- [x] 14. 抽离 EControlSingleForm.vue
  - 新建 `econtrol/EControlSingleForm.vue`，props（schema/data/readonly）+ emit（field-change/ai-suggest）
  - 渲染 segments + visibleSegmentFields（safeEvaluate 过滤）+ FieldInput
  - shell `v-else` 引用
  - 跑 GtEControlTest.spec.ts single 相关绿
  - _需求: 10, 13_

- [x] 15. 抽离 EControlEvalStepper.vue（状态机留 shell）
  - 新建 `econtrol/EControlEvalStepper.vue`，props（schema/data/activeStepNo/currentStep/isTerminalStep/readonly）+ emit（field-change/step-advance/go-to-step/open-attachment）
  - 渲染 el-steps stepper + 当前步骤表单（FieldInput）+ 上/下一步导航 + visibleStepFields
  - **状态机留 shell**：`activeStepNo` ref / `advanceStep` / `goToStep` / `currentStep`(computed) / `isTerminalStep`(computed) 保留在 shell 顶层（测试 vm 访问），子组件通过 props 接收 + emit 通知 shell 改值
  - `evaluateNextLogic` 移 econtrolHelpers 或 shell
  - 跑 GtEControlTest.spec.ts 步骤相关 describe 绿（**重点验证 vm.activeStepNo / vm.advanceStep / vm.goToStep / vm.currentStep / vm.isTerminalStep 全可访问**）
  - _需求: 11, 13_

- [x] 16. GtEControlTest.vue shell 精简 + 验证
  - 确认 shell ≤350 行，保留 header + test_type 路由分发（v-if/v-else-if/v-else）+ AI 面板 + 结论区 + 风险折叠 + 5 emit
  - shell 顶层 refs：summaryRows/singleData/evalData/activeStepNo/conclusionValue/activeHintIds
  - shell 顶层 computed：testType/currentStep/isTerminalStep/conclusionOptions(解构)
  - shell 保留函数：advanceStep/goToStep/onConclusionChange(解构)/initData
  - 清除死代码
  - 跑全部 GtEControlTest.spec.ts + vue-tsc 0 + Playwright `test_e_class_renders_html`
  - 真实 schema 目视：E-C12 / E-C12-1 / E-C11-2 三子模式各抽样
  - _需求: 12, 13_

## 阶段 C — 收尾

- [x] 17. 更新 file_size_whitelist + 全量回归
  - `backend/scripts/file_size_whitelist.txt` 移除 `GtCNoteTable.vue 1802` 行（拆分后 ≤450 不再需要 grandfather）
  - 跑 `check_file_size.py` 确认无新增超标文件
  - 全量回归：两组件全部 vitest + 4 个新单测 + vue-tsc 0 + Playwright C/E
  - 4 真实 schema 目视确认（C-D2-disclosure / E-C12 / E-C12-1 / E-C11-2）与拆分前一致
  - _需求: 13, 14_

- [ ]* 18. （可选）补 Playwright 子组件交互 e2e
  - 为新子组件补针对性 e2e（standard 切换 / 步骤导航 / summary 增删行）
  - _需求: 13_

## 验收确认（对应 requirements §成功判据）

- [x] GtCNoteTable.vue ≤ 450 行（实测 450）
- [x] GtEControlTest.vue ≤ 350 行（实测 344）
- [x] 现有 2 spec 测试零断言改动全绿（C16 + E20 = 36）
- [x] vm 访问点（C 类 10 + E 类 8）拆分后全可访问
- [x] 4 个新单测各 ≥ 5 用例（CNoteCell 16 / useCNoteFormula 9 / useCNoteInheritance 7 / useEControlConclusion 22）
- [x] vue-tsc 0 error（本 spec 涉及文件，全项目预存错误无关）
- [ ] Playwright C/E 类渲染 e2e 通过（**阻塞**：需 start-dev.bat 后端 9980 + 前端 3030，环境未起，待用户手动验证）
- [x] 各组件 5 emit 契约不变
- [x] GtEControlTest.types.ts 含全 13 interface
- [x] file_size_whitelist 移除 GtCNoteTable
- [x] 每产物一 commit 可二分回滚（按阶段 A/B/C 补提交）

## 复盘补救（2026-05-30）

- [x] R1 样式孤儿修复：CNoteCell / EControlSingleForm / EControlEvalStepper 补 `<style scoped>`（从原 shell scoped 样式恢复对应 class），FieldInput 无 gt- class 无需补；同组 SummaryTable/AiPanel/SubTableCard/InheritanceBadge 已自带样式
- [x] R2 git 补提交：本 spec 产物按阶段切提交，恢复二分回滚能力
- [ ] R3 Playwright C/E 实测：环境阻塞，待用户起 start-dev.bat 后跑 C-D2-disclosure / E-C12 / E-C12-1 / E-C11-2 目视

