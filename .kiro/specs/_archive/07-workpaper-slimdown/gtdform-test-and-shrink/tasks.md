# 实施计划：D 类渲染器补测 + 拆分（gtdform-test-and-shrink）

## 概述

核心方法论：**测试先行，再拆分**。按组件逐个推进（Review → Confirmation → Paragraph），每个组件内部严格"先测后拆"。

## 任务

- [x] 1. GtDFormReview 测试补齐（前置，必须先于拆分）
  - [x] 1.1 创建 `GtDForm/__tests__/GtDFormReview.spec.ts`
    - 状态机流转测试：draft→review / review→approved / 非法转换拒绝
    - 签字逻辑测试：onSignClick 成功签字 / canUnsign 边界（最后签字可撤 / 非最后不可撤）
    - 字段联动测试：setStepField 触发 checklist 更新 / onChecklistChange 联动
    - debounce save 测试：修改字段后 save payload 包含 dirty 字段、不含未修改字段
    - 复用 GtDFormQA.spec.ts 范式（Element Plus stubs + fake timers + mount props）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [x] 1.2 验证 vitest 该文件 0 fail
    - `npx vitest run audit-platform/frontend/src/components/workpaper/GtDForm/__tests__/GtDFormReview.spec.ts`
    - _Requirements: 1.5_

- [x] 2. GtDFormConfirmation 测试补齐
  - [x] 2.1 创建 `GtDForm/__tests__/GtDFormConfirmation.spec.ts`
    - 函证状态切换测试：sent→received→reconciled / exception 分支
    - 差异调节计算测试：金额差异 / 百分比差异
    - save payload 测试：状态切换后 payload 结构正确
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 2.2 验证 vitest 该文件 0 fail
    - _Requirements: 2.4_

- [x] 3. GtDFormParagraph 测试补齐
  - [x] 3.1 创建 `GtDForm/__tests__/GtDFormParagraph.spec.ts`
    - 段落渲染测试：markdown 内容正确输出到 DOM
    - 变量插值测试：`{{project_name}}` 等模板变量替换为 props 中的项目上下文值
    - readonly 模式测试：readonly=true 时编辑控件 disabled / 不可交互
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 3.2 验证 vitest 该文件 0 fail
    - _Requirements: 3.4_

- [x] 4. Checkpoint — 测试全绿
  - 运行 `npx vitest run` 确保 3 个新测试文件 + 现有测试 0 fail
  - vue-tsc 0 errors（确认测试文件无类型问题）

- [x] 5. GtDFormReview 拆分
  - [x] 5.1 抽取 `useReviewStateMachine.ts`
    - 包含：onTransitionClick / canTransition / getAvailableTransitions / 审计日志
    - 参数：props（wpDetail / parsedData）+ emit
    - 返回：currentState / availableTransitions / transition()
    - _Requirements: 4.2_
  - [x] 5.2 抽取 `useReviewSignature.ts`
    - 包含：onSignClick / canUnsign / signatureHistory / 撤销规则
    - _Requirements: 4.2_
  - [x] 5.3 抽取 `useReviewFields.ts`
    - 包含：setStepField / onChecklistChange / computedFields / dirty tracking
    - _Requirements: 4.2_
  - [x] 5.4 重写 GtDFormReview.vue 为 shell
    - import 3 composable → 实例化（按拓扑顺序）→ template 绑定
    - 目标 ≤ 400 行
    - _Requirements: 4.1_
  - [x] 5.5 验证 0 回归
    - vitest GtDFormReview.spec.ts 0 fail + vue-tsc 0 errors
    - _Requirements: 4.3, 4.4_

- [x] 6. GtDFormConfirmation 拆分
  - [x] 6.1 抽取 `useConfirmationState.ts`
    - 包含：状态切换 / 可用操作计算
    - _Requirements: 5.2_
  - [x] 6.2 抽取 `useConfirmationFields.ts`
    - 包含：字段填充 / 差异调节 / 金额计算 / save payload
    - _Requirements: 5.2_
  - [x] 6.3 重写 GtDFormConfirmation.vue 为 shell（≤400 行）
    - _Requirements: 5.1_
  - [x] 6.4 验证 0 回归
    - vitest GtDFormConfirmation.spec.ts 0 fail + vue-tsc 0 errors
    - _Requirements: 5.3, 5.4_

- [x] 7. GtDFormParagraph 拆分
  - [x] 7.1 抽取 `useParagraphVariables.ts`
    - 包含：变量插值 / 上下文注入 / 模板解析
    - _Requirements: 6.2_
  - [x] 7.2 重写 GtDFormParagraph.vue 为 shell（≤400 行）
    - _Requirements: 6.1_
  - [x] 7.3 验证 0 回归
    - vitest GtDFormParagraph.spec.ts 0 fail + vue-tsc 0 errors
    - _Requirements: 6.3, 6.4_

- [x] 8. 白名单基线更新
  - [x] 8.1 更新 `file_size_whitelist.txt`
    - GtDFormReview：1670 → 实测值+8%
    - GtDFormConfirmation：如已登记则收紧，未登记则新增
    - _Requirements: 7.1_
  - [x] 8.2 验证 pre-commit check_file_size 全绿
    - _Requirements: 7.2_

- [x] 9. Final Checkpoint
  - vitest 全量 0 fail
  - vue-tsc 0 errors
  - check_file_size 全绿
  - 3 个 D 类组件均 ≤ 400 行
  - 6 个 composable 文件存在且被 shell import

## 说明

- 任务 1-3（测试）是任务 5-7（拆分）的**硬前置**——不可跳过或并行
- 测试范式复用 GtDFormQA.spec.ts（Element Plus stubs + fake timers + mount props）
- 拆分时严格遵守 setup const 拓扑顺序铁律
- C/E 类已由 gt-c-note-table-shrink spec 完成，本 spec 不涉及
