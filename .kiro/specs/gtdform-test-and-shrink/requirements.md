# 需求文档：D 类渲染器补测 + 拆分

## 引言

D 类底稿渲染器（GtDFormReview / GtDFormConfirmation / GtDFormParagraph）共 3982 行零单测，承载复核流程、函证、段落渲染等核心交互逻辑。无测试的大组件违反"骨架未跑测试≠完成"铁律，且让后续拆分变成盲拆。本 spec 先补测试（回归保护），再拆分（降到 ≤400 行 shell）。

## 需求

### 需求 1：GtDFormReview 测试补齐

**用户故事**：作为底稿模块维护者，我希望 GtDFormReview（1670 行复核流程渲染器）有单测覆盖关键交互逻辑，以便后续拆分有回归保护。

**验收标准**：
1. WHEN GtDFormReview.spec.ts 运行，THEN SHALL 覆盖状态机流转（draft→review→approved 至少 3 个转换）
2. WHEN GtDFormReview.spec.ts 运行，THEN SHALL 覆盖签字/撤销逻辑（onSignClick 成功 + canUnsign 边界）
3. WHEN GtDFormReview.spec.ts 运行，THEN SHALL 覆盖字段联动（setStepField 触发 checklist 更新）
4. WHEN GtDFormReview.spec.ts 运行，THEN SHALL 覆盖 debounce save payload 结构正确性
5. WHEN vitest 运行该测试文件，THEN SHALL 0 fail

### 需求 2：GtDFormConfirmation 测试补齐

**用户故事**：作为底稿模块维护者，我希望 GtDFormConfirmation（1434 行函证渲染器）有单测覆盖关键交互。

**验收标准**：
1. WHEN GtDFormConfirmation.spec.ts 运行，THEN SHALL 覆盖函证状态切换（sent→received→reconciled）
2. WHEN GtDFormConfirmation.spec.ts 运行，THEN SHALL 覆盖差异调节计算
3. WHEN GtDFormConfirmation.spec.ts 运行，THEN SHALL 覆盖 save payload 结构
4. WHEN vitest 运行该测试文件，THEN SHALL 0 fail

### 需求 3：GtDFormParagraph 测试补齐

**用户故事**：作为底稿模块维护者，我希望 GtDFormParagraph（878 行段落渲染器）有单测覆盖关键交互。

**验收标准**：
1. WHEN GtDFormParagraph.spec.ts 运行，THEN SHALL 覆盖段落渲染（markdown 内容正确输出）
2. WHEN GtDFormParagraph.spec.ts 运行，THEN SHALL 覆盖变量插值（模板变量替换为项目上下文值）
3. WHEN GtDFormParagraph.spec.ts 运行，THEN SHALL 覆盖 readonly 模式（编辑控件不可交互）
4. WHEN vitest 运行该测试文件，THEN SHALL 0 fail

### 需求 4：GtDFormReview 拆分

**用户故事**：作为底稿模块维护者，我希望 GtDFormReview 从 1670 行拆分为 shell（≤400）+ composable，以便职责单一、可维护。

**验收标准**：
1. WHEN 拆分完成，THEN GtDFormReview.vue SHALL ≤ 400 行
2. WHEN 拆分完成，THEN SHALL 存在 useReviewStateMachine / useReviewSignature / useReviewFields 三个 composable
3. WHEN 拆分完成，THEN 需求 1 的所有测试 SHALL 0 回归
4. WHEN 拆分完成，THEN vue-tsc SHALL 0 errors

### 需求 5：GtDFormConfirmation 拆分

**用户故事**：作为底稿模块维护者，我希望 GtDFormConfirmation 从 1434 行拆分为 shell + composable。

**验收标准**：
1. WHEN 拆分完成，THEN GtDFormConfirmation.vue SHALL ≤ 400 行
2. WHEN 拆分完成，THEN SHALL 存在 useConfirmationState / useConfirmationFields 两个 composable
3. WHEN 拆分完成，THEN 需求 2 的所有测试 SHALL 0 回归
4. WHEN 拆分完成，THEN vue-tsc SHALL 0 errors

### 需求 6：GtDFormParagraph 拆分

**用户故事**：作为底稿模块维护者，我希望 GtDFormParagraph 从 878 行拆分为 shell + composable。

**验收标准**：
1. WHEN 拆分完成，THEN GtDFormParagraph.vue SHALL ≤ 400 行
2. WHEN 拆分完成，THEN SHALL 存在 useParagraphVariables composable
3. WHEN 拆分完成，THEN 需求 3 的所有测试 SHALL 0 回归
4. WHEN 拆分完成，THEN vue-tsc SHALL 0 errors

### 需求 7：白名单基线更新

**验收标准**：
1. WHEN 拆分完成，THEN file_size_whitelist.txt 中 GtDFormReview 基线 SHALL 从 1670 收紧到 ≤ 实测值+8%
2. WHEN pre-commit check_file_size 运行，THEN SHALL 全绿

## 范围边界

- 不改 GtDFormQA / GtDFormTable（已有测试或临界可接受）
- 不改 GtCNoteTable / GtEControlTest（已由 gt-c-note-table-shrink 完成）
- 不改业务逻辑（纯结构拆分 + 测试补齐）
- 测试必须先于拆分（需求 1-3 是需求 4-6 的前置）
