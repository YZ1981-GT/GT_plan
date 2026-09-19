# Implementation Plan: D1-16 坏账准备转回/核销检查表

## Overview

将 D1-16 转回/核销检查表从 `useD1NotesReceivable.ts` 拆分为独立子组件 `D1TabWriteoffCheck.vue`(~300行) + 独立 composable `useD1WriteoffCheck.ts`(~200行)。双段表格(转回8列+核销5列)+审计说明/结论+跨Spec校验+预警系统。TypeScript + Vue 3 + Element Plus。

## Tasks

- [x] 1. 创建 useD1WriteoffCheck composable 核心逻辑
  - [x] 1.1 定义类型接口和纯函数
    - 创建 `audit-platform/frontend/src/components/workpaper/composables/useD1WriteoffCheck.ts`
    - 导出 `ReversalRow`、`WriteoffRow`、`RecoveryMethod`、`NoteNature` 类型
    - 导出 `RECOVERY_METHODS`、`NOTE_NATURES` 枚举常量
    - 实现纯函数：`parseNum`、`sumArray`、`isReversalExceedsProvision`、`isWriteoffExceedsProvision`、`getMissingReversalFields`、`getMissingWriteoffFields`
    - _Requirements: 11.2, 3.1, 6.1, 6.2_

  - [x] 1.2 实现 composable 主体：行CRUD + SUM公式 + 持久化
    - 实现 `useD1WriteoffCheck(options)` 函数签名（接收 allResponses/saveImmediate/saveDebouncedText 等）
    - 实现 `reversalRows` 从 allResponses Map 解析 JSON（key=`D1-writeoff-reversal-rows`）
    - 实现 `writeoffRows` 从 allResponses Map 解析 JSON（key=`D1-writeoff-writeoff-rows`）
    - 实现 `addReversalRow`/`removeReversalRow`/`updateReversalRow` 带 debounce 保存
    - 实现 `addWriteoffRow`/`removeWriteoffRow`/`updateWriteoffRow` 带 debounce 保存
    - 实现 `reversalTotalE`/`reversalTotalF`/`writeoffTotalC` computed SUM
    - 实现汇总写出：`D1-writeoff-reversal-total`/`D1-writeoff-writeoff-total` debounce 保存
    - 实现 `auditNote`/`auditConclusion` 双向绑定 + saveDebouncedText
    - _Requirements: 2.1, 5.1, 9.5, 9.6, 9.7, 10.3, 10.4, 10.5, 11.2, 11.3, 11.4_

  - [x] 1.3 实现跨Spec校验和预警逻辑
    - 实现 `d14ReversalTotal` computed 从 allResponses 读取 `D1-adj-bad-debt-reversal`
    - 实现 `d14WriteoffTotal` computed 从 allResponses 读取 `D1-adj-bad-debt-writeoff`
    - 实现 `eclCurrentTotal` computed 从 allResponses 读取 `D1-ecl-total-current`
    - 实现 `reversalDiff`/`writeoffDiff` computed（本表合计 - D1-4合计，null 当未加载）
    - 实现 `reversalExceedsProvision(row)` 和 `writeoffExceedsProvision` computed
    - 实现 `missingReversalFields(row)`/`missingWriteoffFields(row)` 方法
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.4, 10.1, 10.2_

  - [x]* 1.4 Write property tests for P1 (Reversal SUM) and P2 (Writeoff SUM)
    - 创建 `audit-platform/frontend/src/components/workpaper/composables/__tests__/useD1WriteoffCheck.spec.ts`
    - **Property 1: Reversal SUM 合计行公式正确性**
    - **Validates: Requirements 2.1**
    - **Property 2: Writeoff SUM 合计行公式正确性**
    - **Validates: Requirements 5.1**

  - [x]* 1.5 Write property test for P3 (addRemove 动态行增删计数不变量)
    - **Property 3: 动态行增删计数不变量**
    - **Validates: Requirements 1.3, 4.3**

  - [x]* 1.6 Write property test for P4 (reversalExceedsProvision 判定正确性)
    - **Property 4: reversalExceedsProvision 判定正确性**
    - **Validates: Requirements 3.1**

  - [x]* 1.7 Write property test for P5 (JSON Round-Trip 序列化完整性)
    - **Property 5: JSON Round-Trip 序列化完整性**
    - **Validates: Requirements 9.5**

  - [x]* 1.8 Write property test for P6 (negativeBrackets 负数金额括号格式)
    - **Property 6: 负数金额括号格式**
    - **Validates: Requirements 12.2**

- [x] 2. Checkpoint - 确认 composable 测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 创建 D1TabWriteoffCheck.vue 组件
  - [x] 3.1 搭建组件骨架和双模式切换
    - 创建 `audit-platform/frontend/src/components/workpaper/d1/D1TabWriteoffCheck.vue`
    - 定义 Props 接口（wpId/projectId/allResponses/isReadonly/displayPrefs）
    - 实现 el-segmented 双模式切换（结构化视图 | 在线编辑）
    - 实现 el-skeleton 加载态
    - 实现 OnlyOffice 降级逻辑（OO 不可用时禁用在线编辑 + tooltip）
    - 集成 `useD1WriteoffCheck` composable
    - _Requirements: 9.1, 9.4, 12.6_

  - [x] 3.2 实现 Section 1 转回检查表（8列 el-table + 动态行）
    - 渲染区段标题"(一)本期重要的坏账准备转回检查"
    - 渲染计数标签"共N笔转回，合计金额XXX元"
    - 实现 8 列 el-table：A单位名称(el-input)/B转回原因(textarea)/C收回方式(el-select RECOVERY_METHODS)/D原依据(textarea)/E转回金额(number+fmtAmount)/F原计提(number+fmtAmount)/G合理性分析(textarea)/H索引号(GtIndexChip)
    - 实现操作列删除按钮 + "添加转回项"按钮
    - 实现金额列右对齐、文本列左对齐、textarea min-height:60px
    - 实现合计行（灰色背景不可编辑：E=reversalTotalE, F=reversalTotalF）
    - 实现核对区：本表转回合计 vs D1-4转回变动合计 → 差异（红色高亮 if ≠0）
    - 实现 D1-4 未加载时"-"占位+黄色三角警告图标
    - 实现 E>F 时橙色边框高亮 + tooltip"转回金额超过原计提金额，请核实"
    - 实现必填提示：amount>0 时 reason/analysis 为空显示红色星号
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 12.1, 12.2, 12.3, 12.4_

  - [x] 3.3 实现 Section 2 核销检查表（5列 el-table + 动态行）
    - 渲染区段标题"(二)本期重要的核销应收票据检查"（el-divider 分隔）
    - 渲染计数标签"共N笔核销，合计金额XXX元"
    - 实现 5 列 el-table：A单位名称(el-input)/B性质(el-select NOTE_NATURES)/C核销金额(number+fmtAmount)/D核销原因(textarea)/E核销程序(textarea)
    - 实现操作列删除按钮 + "添加核销项"按钮
    - 实现金额列右对齐、文本列左对齐、textarea min-height:60px
    - 实现合计行（灰色背景不可编辑：C=writeoffTotalC）
    - 实现核对区：本表核销合计 vs D1-4核销变动合计 → 差异（红色高亮 if ≠0）
    - 实现 D1-4 未加载时"-"占位+黄色三角警告图标
    - 实现 ECL 预警：writeoffExceedsProvision 时显示橙色预警"⚠️ 核销金额超过本期计提总额..."
    - 实现必填提示：amount>0 时 reason/procedure 为空显示红色星号
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 12.1, 12.2, 12.3, 12.5, 12.7_

  - [x] 3.4 实现 Section 3/4 审计说明和审计结论
    - 渲染"三、审计说明"区段标题 + textarea（min-height:120px）
    - 实现🤖AI生成按钮（disabled 占位）+ 💬复核对话按钮（inject openReviewDialog）
    - 渲染"四、审计结论"区段标题 + textarea（min-height:120px）
    - 实现🤖AI生成按钮（disabled 占位）+ 💬复核对话按钮
    - 实现编制提示折叠区（`<details>` 蓝色左边线+浅蓝背景，默认收起：转回条件/核销审批/关联方/损益）
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 8.1, 8.2, 8.3, 8.5, 8.6_

  - [x]* 3.5 Write unit tests for component rendering
    - 测试双模式切换逻辑
    - 测试转回/核销表格渲染（含合计行）
    - 测试预警高亮显示条件
    - _Requirements: 1.2, 4.2, 12.6_

- [x] 4. 集成到主入口 GtD1NotesReceivable.vue
  - [x] 4.1 在主入口 el-tabs 中新增 D1-16 tab-pane
    - 在 `GtD1NotesReceivable.vue` 中 import D1TabWriteoffCheck
    - 添加新 el-tab-pane（label="坏账转回/核销检查"）
    - 传递 props：wpId/projectId/allResponses/isReadonly/displayPrefs
    - _Requirements: 11.1_

- [x] 5. Final checkpoint - 确认所有测试通过并集成完整
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. P1 差异不一致时"同步到D1-4"
  - [x] 6.1 在 useD1WriteoffCheck.ts 中实现同步逻辑
    - syncReversalToD14()：将reversalTotalE写入D1-adj-bad-debt-reversal + saveImmediate
    - syncWriteoffToD14()：将writeoffTotalC写入D1-adj-bad-debt-writeoff + saveImmediate
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x] 6.2 在 D1TabWriteoffCheck.vue 核对区添加"同步到D1-4"按钮
    - 仅当差异≠0时显示按钮
    - 点击→确认弹窗→调用syncToD14→差异computed自动刷新→ElMessage.success
    - _Requirements: 13.5, 13.6_

- [x] 7. P1 AI辅助生成审计说明/结论
  - [x] 7.1 启用 D1-16 的🤖AI按钮
    - Section 3：收集转回/核销笔数+金额+校验结果+预警→调用/ai-generate
    - Section 4：收集审计说明+校验结果→调用/ai-generate
    - 复用a171/ai-generate模式
    - AI不可用时disabled + tooltip
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 实现语言：TypeScript（Vue 3 Composition API + Element Plus）
- 测试框架：vitest + fast-check (PBT)
- 6 个 Property 分别对应 P1~P6，每个 100+ iterations
- 跨Spec数据通过同一 allResponses Map computed 响应式读取，无需额外 API
- 持久化复用 checklist_responses 表 + useD1FormData 基础设施
