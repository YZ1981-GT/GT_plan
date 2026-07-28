# Design Document

## Overview

G0 投资循环有两张差异核对表（其他枢纽只有一张 X0-4）：证券投资（数量/市价/公允价值三维）与非证券投资（持股比例/投资金额/投资条款三维）。本设计在**可达性已由 `confirmation-hub-workbench-tabs` Req10 修复**的前提下，做两表的结构正确性——证券表补 5 列 + 「是否需要调账」改判断列，非证券表建三维模型（不套用共享单维 `diffReconcile`）。

**实证基线（读码确认）**：
- 证券表专属组件 `g0-confirmation/diffSecurities/`，`SecuritiesDiffRow`（`diff-securities-v1`）现有：security_name/code/type + qty(confirmed/booked/diff) + unit_fv(confirmed/booked/diff) + market_value(confirmed/booked/diff) + diff_reason/adjustment_note/verify_conclusion/remark。**缺** 询证函索引号/资金账号/开户名称/账面余额/相关支持性证据；`adjustment_note` 是自由文本（源模板「是否需要调账」是判断列）；`security_code`/`security_type` 是源外增强。
- 非证券表被指向共享 `diffReconcile`（`DiffReconcileRow` 单维金额：sent/reply/difference），**持股比例/投资条款无处落**。
- 共享 `diffReconcile` 被 D0/E0/F0/H0/K0/L0 六枢纽用 → 零回归红线，本设计一行不改它。

**第一性约束**：证券表 additive 补列（`diff-securities-v1` 数据读回不丢）；非证券表**新建独立组件与类型**（不改共享 `diffReconcile`）；两表列不臆造，对源模板 17/15 列。

## Architecture

```
G0 差异核对（Req10 修复可达后）
├── 证券投资差异核对表G0-3（证券投资）
│     → confirmation-diff-securities（既有组件，本 spec additive 补 5 列 + 调账判断列）
└── 非证券投资差异核对表G0-4(非证券投资)
      → 现指向共享 diffReconcile（单维，装不下三维）
      → 本 spec 新建 g0-diff-nonsecurities 专属组件 + NonSecuritiesDiffRow 三维类型
      → wp_code_overrides sheet_name 精确 override 从 confirmation-diff-reconcile
         改指向新 componentType（可达性 override 由 Req10 落，本 spec 定最终 componentType）

共享 diffReconcile：D0/E0/F0/H0/K0/L0 六枢纽继续用，一行不改（零回归红线）
```

**与 `confirmation-hub-workbench-tabs` Req10 的接力**：Req10 保证 G0-4 先渲染成 `confirmation-diff-reconcile` 不落兜底（可达）；本 spec 建好 `g0-diff-nonsecurities` 后，把 G0-4 的 sheet_name override 改指向它。两 spec 顺序：Req10 先（可达），本 spec 后（结构）。

### 关键决策

**决策 1：证券表 additive 补 5 列 + 调账列改判断列**

`SecuritiesDiffRow` additive 补 `confirm_index`（询证函索引号）/ `fund_account`（资金账号）/ `account_holder`（开户名称）/ `booked_balance`（账面余额）/ `support_evidence`（相关支持性证据）。新增 `need_adjust: '是'|'否'|'待定'`（判断列，`adjustment_note` 保留为说明文本）；既有已录 `adjustment_note` 文本 → 迁移逻辑：非空且未设 `need_adjust` 时映射为 `待定` 并保留原文（不丢，Requirement 1.3）。`security_code`/`security_type` 保留登记源外（Requirement 1.4）。

**决策 2：非证券表新建三维模型专属组件（不套 diffReconcile）**

`diffReconcile` 单维金额（sent/reply/difference）无法承载「持股比例/投资金额/投资条款 × 账面·回函·差异」。新建：
- `g0-confirmation/diffNonSecurities/nonSecuritiesDiffTypes.ts`：`NonSecuritiesDiffRow`（三维，见 Data Models）
- `GtG0DiffNonSecurities.vue` + `useG0DiffNonSecurities.ts`
- 新 componentType `confirmation-diff-nonsecurities`，注册 `htmlRendererRegistry` + `wp_code_overrides` sheet_name 精确 override
- payload `_format: 'diff-nonsecurities-v1'`

**三维差异计算规则**（Requirement 7.1）：
- 数值维（投资金额）：`difference = booked − reply`（符号与口径同 diffReconcile）
- 比例维（持股比例）：以百分点计 `ratio_diff = booked_ratio − reply_ratio`（scale 明确为百分比数值，如 30 表示 30%）
- 条款维（投资条款）：不做数值相减，`term_match: '一致'|'不一致'` + `term_diff_note` 文本（Requirement 2.3）

**决策 3：非证券既有数据迁移路径**

若既有项目已把非证券差异录在共享 `diffReconcile`（`diff-reconcile-v1`），提供读取兼容：新组件 hydrate 时可读旧 `diff-reconcile-v1` 的 sent/reply/difference → 映射到投资金额维（booked/reply/difference），持股比例与条款维为空（Requirement 2.6）。不静默丢弃。实证 G0 系列 checklist_responses 行数在 M0 核实（大概率近零，同 E0）。

**决策 4：上下游关联走 confirm_index**

两表行标注 `confirm_index` 关联 G0-1；G0-1 match_status='不符' 行可带入或提示待核对（Requirement 3.1/3.2）；结论「需要调账」经 `need_adjust` 可被下游（调整分录/未更正错报）消费或提示 + 索引（Requirement 3.3）。

**决策 5：两表分工按被投资单位性质，不双写**

底稿内明示证券投资 / 非证券投资适用范围；同一被投资单位归一表；性质不明允许审计师选归属，不自动双写（Requirement 4）。差异合计分别统计不隐式相加（Requirement 4.3）。

## Components and Interfaces

### 改造（证券表）

| 组件 | 动作 |
|---|---|
| `diffSecuritiesTypes.ts` | `SecuritiesDiffRow` additive 补 5 列 + `need_adjust`；每列注释源出处 |
| `diffSecurities/` grid | 渲染 5 新列（按源 17 列顺序）；「是否需要调账」改点选判断列；从 G0-1 带入 confirm_index 去重 |

### 新增（非证券表）

| 文件 | 职责 |
|---|---|
| `diffNonSecurities/nonSecuritiesDiffTypes.ts` | `NonSecuritiesDiffRow` 三维类型 + payload `diff-nonsecurities-v1` |
| `GtG0DiffNonSecurities.vue` + `useG0DiffNonSecurities.ts` | 三维核对渲染 + 计算 + 从 G0-1 带入 + 旧 diffReconcile 数据 hydrate |
| `htmlRendererRegistry.ts` | 注册 `confirmation-diff-nonsecurities` |
| `wp_code_overrides.json` | `函证差异核对表G0-4(非证券投资)` → `confirmation-diff-nonsecurities`（接力 Req10） |
| `g0DiffSourceManifest.ts` | 两表源模板 17/15 列清单（契约守卫基准）+ 源外字段登记 |

### 不改（零回归红线）

`diffReconcile/` 组件与 `DiffReconcileRow`（六枢纽共用）—— 一行不动。

## Data Models

### SecuritiesDiffRow additive 补列（决策 1）

| 新字段 | 类型 | 源出处 |
|---|---|---|
| `confirm_index` | string | G0-3「询证函索引号」 |
| `fund_account` | string | G0-3「资金账号」 |
| `account_holder` | string | G0-3「开户名称」 |
| `booked_balance` | number | G0-3「账面余额」 |
| `support_evidence` | string | G0-3「相关支持性证据」 |
| `need_adjust` | '是'\|'否'\|'待定' | G0-3「是否需要调账」（判断列）|

> `adjustment_note` 保留为说明文本；`security_code`/`security_type` 登记源外增强。

### NonSecuritiesDiffRow（新建，三维，diff-nonsecurities-v1）

```ts
interface NonSecuritiesDiffRow {
  _row_id?: string
  seq?: number
  confirm_index?: string        // 关联 G0-1
  entity_name?: string          // 被投资单位
  // 维度①持股比例（百分点）
  booked_ratio?: number         // 账面持股比例 %
  reply_ratio?: number          // 回函持股比例 %
  ratio_diff?: number           // = booked_ratio − reply_ratio（自动，百分点）
  // 维度②投资金额（数值）
  booked_amount?: number        // 账面投资金额
  reply_amount?: number         // 回函投资金额
  amount_diff?: number          // = booked_amount − reply_amount（自动）
  // 维度③投资条款（文本，不做数值相减）
  booked_term?: string          // 账面投资条款
  reply_term?: string           // 回函投资条款
  term_match?: '一致' | '不一致'
  term_diff_note?: string
  // 通用
  diff_reason?: string
  need_adjust?: '是' | '否' | '待定'
  adj_ref_index?: string        // 调整分录索引
  support_evidence?: string
  remark?: string
  _source?: string
}
interface NonSecuritiesDiffPayload {
  _format: 'diff-nonsecurities-v1'
  rows: NonSecuritiesDiffRow[]
  conclusion?: string
  audit_note?: string
}
```

> 源模板 15 列，实施 M0 逐列核对确认字段齐全不多不少。

## Correctness Properties

### Property 1: 证券表 additive 读回不丢
`diff-securities-v1` 既有 payload 读取→保存→读取，既有字段值 SHALL 逐字不变。
**Validates: Requirements 1.1**

### Property 2: 证券表调账列改判断且旧文本不丢
`need_adjust` SHALL 为点选枚举；既有非空 `adjustment_note` SHALL 可回显（映射为「待定」+ 保留原文），SHALL NOT 丢失。
**Validates: Requirements 1.3**

### Property 3: 证券表源外字段登记
`security_code`/`security_type` SHALL 在 manifest 登记为源外增强，SHALL NOT 静默删除。
**Validates: Requirements 1.4, 6.3**

### Property 4: 非证券三维计算规则
`amount_diff = booked_amount − reply_amount`（符号固定）；`ratio_diff = booked_ratio − reply_ratio`（百分点）；条款维 SHALL NOT 做数值相减，用 `term_match` + 说明。
**Validates: Requirements 2.1, 2.2, 2.3, 7.1**

### Property 5: 非证券不改共享 diffReconcile
本 spec 落地后 `DiffReconcileRow` 与 `diffReconcile/` 组件 SHALL 逐字不变；D0/E0/F0/H0/K0/L0 差异调节行为不变。
**Validates: Requirements 2.4, 5.1, 5.3, 7.4**

### Property 6: 非证券 15 列不多不少
`g0-diff-nonsecurities` 渲染列 SHALL 与源模板 15 列清单一致（对 manifest），SHALL NOT 新增源模板没有的列。
**Validates: Requirements 2.5, 6.1, 7.2**

### Property 7: 非证券旧数据可回显
既有录在共享 `diff-reconcile-v1` 的非证券差异 SHALL 可 hydrate 到投资金额维（booked/reply/difference），SHALL NOT 静默丢弃。
**Validates: Requirements 2.6**

### Property 8: 上下游 confirm_index 关联
两表行 SHALL 可标注 confirm_index 关联 G0-1；G0-1 不符行 SHALL 可带入或待核对提示；无法自动关联 SHALL 提供手工填索引不静默断链。
**Validates: Requirements 3.1, 3.2, 3.4**

### Property 9: 两表不双写
同一被投资单位 SHALL NOT 被要求在两表同时录入；差异合计 SHALL 分别统计不隐式相加。
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 10: 每列可追溯源出处
两表每列 SHALL 在 `g0DiffSourceManifest` 有出处或登记源外增强。
**Validates: Requirements 6.1, 6.2, 6.3**

## Error Handling

| 场景 | 处理 |
|---|---|
| 证券表旧 payload 缺新列 | 新列 undefined，正常渲染空 |
| 证券表旧 adjustment_note 非空 | 映射 need_adjust=待定 + 保留原文 |
| 非证券旧数据在 diffReconcile | hydrate 到投资金额维，比例/条款空 |
| G0-1 无匹配行 | 手工填 confirm_index，不静默断链 |
| 被投资单位性质不明 | 审计师选归属，不自动双写 |

## Testing Strategy

- **属性测试（fast-check）**：Property 1/7 round-trip 与 hydrate、Property 4 三维计算规则
- **契约测试**：Property 6 非证券 15 列对 manifest、Property 10 每列可追溯、Property 5 diffReconcile 未被改动（diff/grep 断言）、Property 3 源外登记
- **单元测试**：Property 2 调账判断+旧文本、Property 8 confirm_index 关联、Property 9 不双写
- **零回归门**：六枢纽 diffReconcile 相关测试 + 函证域全量前端测试全绿；G0 其余 sheet 行为不变；改动文件 `get_diagnostics` 清 + Vite transform 200
- **Playwright**：G0-3 证券表（5 新列 + 调账判断列）、G0-4 非证券表（三维 + 旧数据 hydrate）各一次；前置 = Req10 已让两表可达

## Migration / Phasing

| 阶段 | 内容 | 可回退 |
|---|---|---|
| **M0** | 两表源模板 17/15 列逐列核对 → `g0DiffSourceManifest` + 源外登记 + G0 系列既有数据行数核实（纯只读） | 无风险 |
| **M1** | 证券表 additive 补 5 列 + 调账判断列（依赖 Req10 已可达）| 独立可回退 |
| **M2** | 非证券三维组件 + 类型 + 注册 + override 接力 Req10 | 独立可回退 |
| **M3** | 上下游 confirm_index 关联 + 两表分工 + 旧数据 hydrate | 可回退 |
| **M4** | 契约/属性/守卫（含 diffReconcile 未改守卫）+ 零回归门 + Playwright | 仅测试 |

**前置**：`confirmation-hub-workbench-tabs` Req10 让 G0-3/G0-4 可达（否则 diffSecurities 零渲染无法验证）。M0 硬前置：列清单未核实不得进 M1。
