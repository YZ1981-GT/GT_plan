# Implementation Plan: ReportView Slimdown

## Overview

纯重构——将 `ReportView.vue`�?944 行）拆分�?orchestrator 主文�?+ 6 composable + 3 子组�?+ 1 外置 CSS，遵循「先测后拆」模式。每步抽取后立即验证 vue-tsc + vitest，确保零功能回归�?

## Tasks

> **执行约束（实施前必读�?*�?
> 1. **行范围仅作参�?*——spec 中的行号是估算，实际以函数名/标签名为准（codegraph/grep 定位），勿死抠行号�?
> 2. **composable 实例传递铁�?*——ReportView �?new �?`rvCtx=useCellSelection()` / `rvPenetrate=usePenetrate()` / `rvComments=useCellComments()` 三个实例（行 ~1876-1878）。抽�?useReportCellActions 时这三个实例**必须作为参数传入**，不可在 composable 内重�?new（否则右键菜单选中�?穿透�?批注态分裂，引入隐性回归）�?
> 3. **git 提交节点**——每�?Checkpoint（Task 3/10/14）后�?commit 提交进度，便于二分定位回归�?
> 4. **对比视图确认**——`MultiYearCompare.vue` 已是独立组件（行 941 import），抽取前先确认对比视图 el-table 是否已被它覆盖，避免重复造组件�?

- [x] 1. 编写特征测试（Characterization Tests）——拆分前锁定纯函数行�?
  - [x] 1.1 创建 `src/views/__tests__/ReportView.characterization.spec.ts`
    - **聚焦纯函�?*（无需 mount 整个组件，避�?mock 35+ 依赖的脆弱测试）�?
      - 行类型判�?6 种（getRowType: header/total/special/manual/zero/data�?
      - 权益�?span-method（equitySpanMethod 对分类行返回 colspan�?
      - 跨表核对 7 条等式计算（crossCheckResults 公式正确性）
      - formatReportAmount 千分�?+ 负数括号
    - **�?*：Tab 切换触发 fetchReport / 刷新按钮�?API / 右键菜单穿�?这类需 mount 的用�?*不在此处**——改为抽取后对应 composable 单测（Task 5.3 useReportData / Task 9.3 useReportCellActions）覆盖，避免在重组件上写脆弱 mount 测试
    - _Requirements: 1.1, 6.1, 6.2_

  - [x]* 1.2 编写 getRowType property-based test
    - **Property 1: Behavioral Equivalence �?getRowType 纯函�?*
    - 使用 fast-check `fc.record(...)` 生成随机 ReportRow，验�?getRowType 返回值属�?6 种合法枚�?
    - `numRuns: 5`
    - **Validates: Requirements 1.1**

  - [x]* 1.3 编写 formatReportAmount property-based test
    - **Property 1: Behavioral Equivalence �?formatReportAmount 纯函�?*
    - 使用 fast-check `fc.oneof(fc.integer(), fc.double(), fc.constant(null), fc.constant(undefined))` 生成随机输入
    - 验证：非 null 数�?�?text 包含千分位或括号格式；null/undefined �?空字符串
    - `numRuns: 5`
    - **Validates: Requirements 1.1**

- [x] 2. CSS 外置（低风险，立即缩�?~484 行）
  - [x] 2.1 �?`<style scoped>` 内容移到 `src/views/report-view.css`
    - 保持所有选择器、类名、`:deep()` 穿透不�?
    - 主文件改�?`<style scoped src="./report-view.css" />`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 2.2 验证 CSS 外置�?vue-tsc + vitest 通过
    - 运行 `npx tsc --noEmit` 零错�?
    - 运行 `npx vitest run` 全部通过
    - 特征测试仍绿
    - _Requirements: 1.2, 1.3_

  - [x]* 2.3 编写 CSS 选择器完备�?property test
    - **Property 4: CSS Selector Completeness**
    - 静态分析：提取�?`<style scoped>` 所有选择器集�?vs `report-view.css` 选择器集合，验证子集关系
    - `numRuns: 5`（对随机子集抽样比对�?
    - **Validates: Requirements 5.3, 5.4**

- [x] 3. Checkpoint �?确认 CSS 外置无回�?
  - `npx vitest run` 全部通过 + `npx tsc --noEmit` 零错�?+ ReportView.vue 行数已减 ~484 �?
  - git �?commit 提交进度（便于二分定位回归）
  - _Requirements: 1.2, 1.3, 5.1_

- [x] 4. 抽取 `useReportColumns` composable
  - [x] 4.1 创建 `src/views/composables/useReportColumns.ts`
    - �?ReportView.vue ~1350�?500 行抽取：eqColumns / eqTotalCols / equitySpanMethod / eqRowClassName / eqCellVal / impIncCols / impDecCols / impRowClassName / getRowType / rowClassName / compareRowClassName / formatReportAmount / getNoteSection / goToNote
    - 定义 `UseReportColumnsOptions` �?`UseReportColumnsReturn` 接口（按 design 文档�?
    - 主文�?import 并调用，仅做编排
    - _Requirements: 3.6, 3.7, 3.8_

  - [x] 4.2 验证抽取�?vue-tsc + vitest 通过
    - _Requirements: 1.2, 1.3_

  - [x]* 4.3 编写 useReportColumns 单元测试
    - 创建 `src/views/composables/__tests__/useReportColumns.spec.ts`
    - 测试 equitySpanMethod / getRowType / formatReportAmount / eqColumns 计算
    - _Requirements: 3.6_

  - [x]* 4.4 编写 equitySpanMethod property-based test
    - **Property 1: Behavioral Equivalence �?equitySpanMethod**
    - fast-check 生成随机 `{row, column, rowIndex, columnIndex}`，验证返�?`{rowspan, colspan}` 值合法（�?�?
    - `numRuns: 5`
    - **Validates: Requirements 1.1, 3.6**

- [x] 5. 抽取 `useReportData` composable
  - [x] 5.1 创建 `src/views/composables/useReportData.ts`
    - �?ReportView.vue ~1200�?810 行抽取：fetchReport / onGenerate / onConsistencyCheck / runBalanceCheck / loadTemplateRows / ensureProjectYear / reloadReportContext / rows / compareRows / loading / genLoading / checkLoading / syncLoading / balanceCheckResult / consistencyResult / tableMaxHeight / activeTabLabel / coverageSummary / projectName / reportScope / templateType / isConsolidated
    - 定义 `UseReportDataOptions` �?`UseReportDataReturn` 接口
    - 主文�?import 并调�?
    - _Requirements: 3.1, 3.7, 3.8_

  - [x] 5.2 验证抽取�?vue-tsc + vitest 通过
    - _Requirements: 1.2, 1.3_

  - [x]* 5.3 编写 useReportData 单元测试
    - 创建 `src/views/composables/__tests__/useReportData.spec.ts`
    - Mock API，验�?fetchReport / onGenerate / loadTemplateRows 调用和状态变�?
    - 含原特征测试移来�?mount 类用例：Tab 切换触发 fetchReport（API 参数正确）、刷新按钮调 generateReports（API + ElMessage）、对比视图合并逻辑（compareRows 结构�?
    - _Requirements: 3.1_

- [x] 6. 抽取 `useReportMapping` composable
  - [x] 6.1 创建 `src/views/composables/useReportMapping.ts`
    - �?ReportView.vue ~1070�?200 行抽取：showMappingDialog / mappingLoading / mappingTab / allMappingRules / allListedOptions / mappingReportTypes / mappingTabLabel / currentMappingRules / currentListedOptions / totalMappedCount / totalRuleCount / loadPresetMappingAll / saveMappingRulesAll / getMappingConfigData / onMappingTemplateApplied
    - 定义 `UseReportMappingOptions` �?`UseReportMappingReturn` 接口
    - 主文�?import 并调�?
    - _Requirements: 3.2, 3.7, 3.8_

  - [x] 6.2 验证抽取�?vue-tsc + vitest 通过
    - _Requirements: 1.2, 1.3_

  - [x]* 6.3 编写 useReportMapping 单元测试
    - 创建 `src/views/composables/__tests__/useReportMapping.spec.ts`
    - Mock API，验�?loadPreset / save / templateApply
    - _Requirements: 3.2_

- [x] 7. 抽取 `useReportCrossCheck` composable
  - [x] 7.1 创建 `src/views/composables/useReportCrossCheck.ts`
    - �?ReportView.vue ~1880�?000 行抽取：crossCheckData / crossCheckLoading / crossCheckResults / loadCrossCheckData
    - 定义 `UseReportCrossCheckOptions` �?`UseReportCrossCheckReturn` 接口
    - 主文�?import 并调�?
    - _Requirements: 3.4, 3.7, 3.8_

  - [x] 7.2 验证抽取�?vue-tsc + vitest 通过
    - _Requirements: 1.2, 1.3_

  - [x]* 7.3 编写 useReportCrossCheck 单元测试
    - 创建 `src/views/composables/__tests__/useReportCrossCheck.spec.ts`
    - Mock API，验�?7 条等式计算逻辑
    - _Requirements: 3.4_

  - [x]* 7.4 编写 crossCheckResults 计算 property-based test
    - **Property 1: Behavioral Equivalence �?跨表核对等式**
    - fast-check 生成随机 BS/IS 行数据，验证 diff = leftValue - rightValue �?passed = (diff === 0)
    - `numRuns: 5`
    - **Validates: Requirements 1.1, 3.4**

- [x] 8. 抽取 `useReportExport` composable
  - [x] 8.1 创建 `src/views/composables/useReportExport.ts`
    - �?ReportView.vue ~2400�?460 行抽取：onExportExcel / onExportAllExcel / copyReportTable / showReportImport / onReportImported
    - 定义 `UseReportExportOptions` �?`UseReportExportReturn` 接口
    - 主文�?import 并调�?
    - _Requirements: 3.5, 3.7, 3.8_

  - [x] 8.2 验证抽取�?vue-tsc + vitest 通过
    - _Requirements: 1.2, 1.3_

  - [x]* 8.3 编写 useReportExport 单元测试
    - 创建 `src/views/composables/__tests__/useReportExport.spec.ts`
    - Mock downloadFileAsBlob，验�?export URL 拼接正确
    - _Requirements: 3.5_

- [x] 9. 抽取 `useReportCellActions` composable
  - [x] 9.1 创建 `src/views/composables/useReportCellActions.ts`
    - �?ReportView.vue ~1860�?400 行抽取：全部 drilldown / lineComp / noteRefs / rvTrace / audit / traceSelect / consolBreakdown / cellFormulaDetail 相关 state + 全部 onRvCell* / onRvCtx* handlers
    - **🔴 关键约束**：`rvCtx`(useCellSelection) / `rvPenetrate`(usePenetrate) / `rvComments`(useCellComments) 三个已有实例**必须从主文件作为参数传入** `UseReportCellActionsOptions`，composable 内部**不可重新 new**（否则单元格选中�?穿透�?批注态分裂，右键菜单失效�?
    - 定义 `UseReportCellActionsOptions`（含 rvCtx/rvPenetrate/rvComments 实例）和 `UseReportCellActionsReturn` 接口
    - 主文�?import 并调�?
    - _Requirements: 3.3, 3.7, 3.8_

  - [x] 9.2 验证抽取�?vue-tsc + vitest 通过
    - 重点验证右键菜单选中/框�?穿�?批注交互无回归（实例传递正确）
    - _Requirements: 1.2, 1.3_

  - [x]* 9.3 编写 useReportCellActions 单元测试
    - 创建 `src/views/composables/__tests__/useReportCellActions.spec.ts`
    - Mock router/API，验�?click/dblclick/contextmenu handlers + onDrilldown API 调用（含原特征测试移来的 mount 类用例）
    - _Requirements: 3.3_

- [x] 10. Checkpoint �?确认全部 composable 抽取完成无回�?
  - `npx vitest run` 全部通过 + `npx tsc --noEmit` 零错�?
  - 确认主文�?script 部分已大幅缩减（仅剩 import + composable 调用编排�?
  - �?useReportData.ts �?400 行，评估是否二次拆分（useReportFetch + useReportGeneration�?
  - git �?commit 提交进度
  - _Requirements: 1.2, 1.3, 2.1_

- [x] 11. 抽取 `ReportEquityTable.vue` 子组�?
  - [x] 11.1 创建 `src/components/report/ReportEquityTable.vue`
    - �?ReportView.vue 模板 ~141�?95 行抽取：权益变动�?el-table 矩阵（含本年/上年动态列、三级表头）
    - 通过 props 接收数据（rows / eqColumns / eqTotalCols / year / tableMaxHeight / cellClassName / fontSize�?
    - 通过 emit 上报事件（cell-click / cell-dblclick / cell-contextmenu�?
    - expose tableRef 供拖选绑�?
    - 保持 GT 紫令牌样式和 GtAmountCell 使用
    - _Requirements: 4.1, 4.4, 4.5, 4.6_

  - [x] 11.2 在主文件中替换原模板片段�?`<ReportEquityTable />` 组件调用
    - _Requirements: 4.1_

  - [x] 11.3 验证抽取�?vue-tsc + vitest 通过
    - _Requirements: 1.2, 1.3_

- [x] 12. 抽取 `ReportImpairmentTable.vue` 子组�?
  - [x] 12.1 创建 `src/components/report/ReportImpairmentTable.vue`
    - �?ReportView.vue 模板 ~296�?40 行抽取：减值准备表 el-table 矩阵（含增加/减少嵌套列）
    - 通过 props 接收数据（rows / impIncCols / impDecCols / tableMaxHeight / cellClassName / fontSize�?
    - 通过 emit 上报事件（cell-click / cell-dblclick / cell-contextmenu�?
    - expose tableRef
    - _Requirements: 4.2, 4.4, 4.5, 4.6_

  - [x] 12.2 在主文件中替换原模板片段�?`<ReportImpairmentTable />` 组件调用
    - _Requirements: 4.2_

  - [x] 12.3 验证抽取�?vue-tsc + vitest 通过
    - _Requirements: 1.2, 1.3_

- [x] 13. 抽取 `ReportDialogs.vue` 子组�?
  - [x] 13.1 创建 `src/components/report/ReportDialogs.vue`
    - �?ReportView.vue 模板 ~571�?30 行抽取：穿透弹窗、构成科目弹窗、审核结果弹窗、溯源弹窗、转换规则弹窗、溯源选择弹窗、附注引�?Drawer、合并明细弹�?
    - 通过 props 接收所�?dialog �?visibility + data（按 design 文档 ReportDialogsProps 接口�?
    - 通过 emit 上报所有事件（�?design 文档 ReportDialogsEmits 接口�?
    - _Requirements: 4.3, 4.4, 4.5, 4.6_

  - [x] 13.2 在主文件中替换原模板片段�?`<ReportDialogs />` 组件调用
    - _Requirements: 4.3_

  - [x] 13.3 验证抽取�?vue-tsc + vitest 通过
    - _Requirements: 1.2, 1.3_

- [x] 14. Checkpoint �?确认全部子组件抽取完成无回归
  - `npx vitest run` 全部通过 + `npx tsc --noEmit` 零错�?
  - �?ReportDialogs.vue �?600 行，拆为 2-3 个独立弹窗组件（ReportDrilldownDialogs / ReportTraceDialogs / ReportMappingDialog�?
  - 确认主文件总行数（含模�?script+style 引用）≤1500
  - git �?commit 提交进度
  - _Requirements: 1.2, 1.3, 2.1, 4.3_

- [x] 15. 最终验�?+ whitelist 基线下调 + HARD_CAP 登记
  - [x] 15.1 确认 ReportView.vue 行数 �?500
    - 运行 `wc -l` 或等效命令确认主文件行数
    - 确认所有抽取文件均 �?500 �?
    - _Requirements: 2.1, 2.4_

  - [x] 15.2 运行 `python backend/scripts/check/check_file_size.py` 确认 exit 0
    - _Requirements: 2.1_

  - [x] 15.3 下调 `backend/scripts/file_size_whitelist.txt` �?ReportView.vue 基线
    - �?`audit-platform/frontend/src/views/ReportView.vue 2848` 改为实际瘦身后行数（±10 行余量）
    - _Requirements: 2.2_

  - [x] 15.4 �?`HARD_CAPS` 字典中登�?ReportView.vue
    - �?`backend/scripts/check/check_file_size.py` �?`HARD_CAPS` dict 中添�?`"audit-platform/frontend/src/views/ReportView.vue": <实际行数+15%余量>`
    - 添加注释说明来源 spec
    - _Requirements: 2.3_

  - [x] 15.5 全量最终验�?
    - `npx tsc --noEmit` 零错�?
    - `npx vitest run` 全部通过（含特征测试 + composable 单测�?
    - `python backend/scripts/check/check_file_size.py` exit 0
    - 确认零功能回归、零 UI 文本变化
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3_

  - [x]* 15.6 编写 file-size invariant property test
    - **Property 2: File Size Invariant**
    - 静态检查：遍历所有抽取文件路径，断言每个文件 �?500 �?
    - `numRuns: 5`（对路径列表随机排列验证�?
    - **Validates: Requirements 2.1, 2.4**

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 遵循「先测后拆」模式：特征测试（Task 1）在所有抽取之前完�?
- CSS 外置（Task 2）最先做——低风险且立即缩�?~484 �?
- 每个 composable/子组件抽取独立一�?task，抽取后立即验证
- Property tests 使用 fast-check，`numRuns: 5`
- 前端测试命令：`npx vitest run`
- 类型检查：`npx tsc --noEmit`（vue-tsc�?
- 文件大小守护：`python backend/scripts/check/check_file_size.py`
