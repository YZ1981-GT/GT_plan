# 设计文档：D 类渲染器补测 + 拆分（gtdform-test-and-shrink）

## 概述

D 类底稿渲染器（销售收入循环）是底稿 HTML 渲染器中最复杂的一族（5 子模式），其中 3 个核心组件共 **3982 行零单测**（GtDFormReview 1670 / GtDFormConfirmation 1434 / GtDFormParagraph 878）。本 spec 的目标是：**先补测试（回归保护），再拆分（降到 ≤400 行 shell + composable）**。

### 范围校准（2026-05-30 实测）

- **C/E 类已由 `gt-c-note-table-shrink` spec 完成拆分**：GtCNoteTable 1803→452 / GtEControlTest 1414→344（远程 origin/main 已合入）。本 spec **不再覆盖 C/E 类**。
- **D 类当前行数**（本分支实测）：GtDFormReview **1670** / GtDFormConfirmation **1434** / GtDFormParagraph **878** / GtDFormQA 1224（已有 27 用例测试，不动）/ GtDFormTable 993（部分测试，不动）
- **核心铁律**：测试必须先于拆分——否则是盲拆，无回归保护

### 已有测试的组件（不动，作为范式参考）

- `GtDFormQA.spec.ts`：27 用例，覆盖业务模式判定 / 状态切换 / save payload
- `GtCNoteTable.spec.ts`：继承规则校验等（已拆分后仍保留）
- `GtEControlTest.spec.ts`：6 步骤决策树

## 现状诊断

### GtDFormReview.vue（1670 行，复核流程）

**职责分析**（script 块逻辑分层）：
- 状态机流转（onTransitionClick / canTransition / getAvailableTransitions）~200 行
- 签字链（onSignClick / canUnsign / signatureHistory）~150 行
- 步骤字段联动（setStepField / onChecklistChange / computedFields）~300 行
- debounce save（autoSave / buildSavePayload / dirty tracking）~150 行
- 模板渲染（template 区域，条件分支多）~600 行
- 其余（props/emits/imports/生命周期）~270 行

**可抽 composable**：
- `useReviewStateMachine`：状态机流转 + 审计日志 + 可用转换计算
- `useReviewSignature`：签字链 + 撤销规则 + 签字历史
- `useReviewFields`：步骤字段 + checklist + 联动逻辑

### GtDFormConfirmation.vue（1434 行，函证流程）

**职责分析**：
- 函证字段填充（confirmationType / counterparty / amounts）~200 行
- 状态切换（sent / received / reconciled / exception）~150 行
- 差异调节（reconciliation fields / variance calculation）~200 行
- save payload 构建 ~100 行
- 模板渲染 ~500 行
- 其余 ~284 行

**可抽 composable**：
- `useConfirmationState`：状态切换 + 可用操作计算
- `useConfirmationFields`：字段填充 + 差异调节 + 金额计算

### GtDFormParagraph.vue（878 行，段落/文档型）

**职责分析**：
- 段落渲染（markdown / rich text / variable interpolation）~300 行
- 变量插值（template variables / project context）~150 行
- readonly 模式切换 ~80 行
- 模板 ~250 行
- 其余 ~98 行

**可抽 composable**：
- `useParagraphVariables`：变量插值 + 上下文注入

## 架构设计

### 拆分策略（统一模式）

每个组件拆分为：**Shell（≤400 行）+ N 个 composable + 可选子组件**

```
GtDFormReview.vue (shell ≤400)
├── useReviewStateMachine.ts (~200)
├── useReviewSignature.ts (~150)
└── useReviewFields.ts (~300)

GtDFormConfirmation.vue (shell ≤400)
├── useConfirmationState.ts (~150)
└── useConfirmationFields.ts (~250)

GtDFormParagraph.vue (shell ≤400)
└── useParagraphVariables.ts (~150)
```

### 关键设计约束

1. **setup const 拓扑顺序铁律**：`const X = useY(..., Z)` 引用的 Z 必须在 X 之前定义。拆分时 composable 实例化顺序必须按依赖拓扑排列。
2. **composable 签名稳定**：每个 composable 接收 `props` + 必要的 reactive 依赖作为参数，返回 template 需要的 ref/computed/methods。
3. **Shell 只做组装**：shell 文件只负责 import composable → 实例化 → template 绑定，不含业务逻辑。
4. **测试先行**：每个组件先写测试（覆盖关键交互），再拆分。拆分后测试必须 0 回归。

### 测试策略

**测试范式**（复用 GtDFormQA.spec.ts 模式）：
- Element Plus stubs（el-form / el-table / el-button 等）
- fake timers（debounce save 测试）
- mount with props（传入 mock parsed_data + wp detail）
- 断言：emit 事件 / save payload 结构 / 状态流转 / 字段联动

**每个组件的测试覆盖重点**：

| 组件 | 测试重点 |
|------|---------|
| GtDFormReview | 状态机流转（draft→review→approved）/ 签字+撤销 / 字段联动 / debounce save payload |
| GtDFormConfirmation | 函证状态切换 / 差异调节计算 / save payload |
| GtDFormParagraph | 段落渲染 / 变量插值 / readonly 模式 |

### 正确性属性

**Property 1: 拆分后行为等价**
对任意 props 输入，拆分后组件的 emit 事件序列与拆分前一致。

**Property 2: 状态机转换合法性**
对任意当前状态，`getAvailableTransitions` 返回的转换集合是该状态的合法出边子集。

**Property 3: 签字链不可逆性**
对任意已签字的步骤，`canUnsign` 仅在该步骤是最后一个签字且无后续步骤签字时返回 true。

**Property 4: save payload 完整性**
对任意字段修改序列，`buildSavePayload` 返回的 payload 包含所有 dirty 字段且不包含未修改字段。

**Property 5: 幂等渲染**
对任意 parsed_data，组件 mount 两次产生相同的 DOM 结构（无副作用累积）。

## 文件变更清单

### 新增文件
- `audit-platform/frontend/src/components/workpaper/GtDForm/composables/useReviewStateMachine.ts`
- `audit-platform/frontend/src/components/workpaper/GtDForm/composables/useReviewSignature.ts`
- `audit-platform/frontend/src/components/workpaper/GtDForm/composables/useReviewFields.ts`
- `audit-platform/frontend/src/components/workpaper/GtDForm/composables/useConfirmationState.ts`
- `audit-platform/frontend/src/components/workpaper/GtDForm/composables/useConfirmationFields.ts`
- `audit-platform/frontend/src/components/workpaper/GtDForm/composables/useParagraphVariables.ts`
- `audit-platform/frontend/src/components/workpaper/GtDForm/__tests__/GtDFormReview.spec.ts`
- `audit-platform/frontend/src/components/workpaper/GtDForm/__tests__/GtDFormConfirmation.spec.ts`
- `audit-platform/frontend/src/components/workpaper/GtDForm/__tests__/GtDFormParagraph.spec.ts`

### 修改文件
- `GtDFormReview.vue`：1670 → ≤400（抽出 3 composable）
- `GtDFormConfirmation.vue`：1434 → ≤400（抽出 2 composable）
- `GtDFormParagraph.vue`：878 → ≤400（抽出 1 composable）
- `backend/scripts/file_size_whitelist.txt`：更新 GtDFormReview 基线（1670→~420）

## 不在范围

- 不改 GtDFormQA / GtDFormTable（已有测试或临界可接受）
- 不改 GtCNoteTable / GtEControlTest（已由 gt-c-note-table-shrink 完成）
- 不改业务逻辑（纯结构拆分 + 测试补齐）
- 不改 DB / router / API
