# Design Document

## Overview

E0 四张发函前清单（E0-3 货币资金 / E0-4 借款 / E0-5 应付银行承兑汇票 / E0-6 理财产品）现走通用 `d-form-table`，其列来自自动生成的 `wp_render_schema/generated/E0.yaml`——**该文件自述草稿**（字段名 `col_a`/`col_d`、label 抓成「编制日期：」「3」），实际是占位表。本设计按源模板给四张清单落真实列，使「清单 → E0-1 带入」有可靠上游。

**实证基线（读码确认）**：
- `E0.yaml` 顶部注释明写「⚠️ 此文件为草稿，关键字段需人工审核」+「columns 字段名（col_a/col_b/... → 业务字段 snake_case）」；`dynamic_table.columns` 是 `col_a`/`col_d` 占位、label 是「编制日期：」「3」（表头行检测错位）。
- 该 YAML 由 `backend/scripts/generate_wp_render_schema.py` 自动生成，含 `_generated` 元数据 + `_note` 待审。
- E0-3/E0-4/E0-5/E0-6 componentType 归属决策（是否 `d-form-table` vs 其他）归 `confirmation-hub-workbench-tabs`（决策 4 定为发函前清单保 `d-form-table`）；本 spec 只做列结构。
- E0 重建（E0-1→summary）与「清单→E0-1 带入」实现归 `confirmation-hub-workbench-tabs` Wave 2；本 spec 只保证清单侧列可用。

**第一性约束**：不改 `confirmation-summary` 与 confirmation-v1；不改后端 render 调度；schema 审定要防「重新生成覆盖审定结果」；不臆造源模板没有的列；不影响其他底稿共用该 schema 文件。

## Architecture

```
E0 四张发函前清单（d-form-table，列来自 render schema）
  现状：E0.yaml.sheets.{sheet_name}.dynamic_table.columns = col_a/col_d 占位（草稿）
  ↓ 本 spec
  ①逐 sheet 对照源模板落真实列（field=业务 snake_case，label=源模板列名，kind/枚举/日期/金额）
  ②防重生成覆盖：审定标记 + generate_wp_render_schema.py 尊重已审定 sheet（或审定结果单独存不被覆盖）
  ③契约守卫：E0 四 sheet 渲染列 == 源模板清单（数据文件登记）

上游可靠性：
  E0-3~E0-6 的「是否函证」列 + 单位名/账号/币种/余额/品种
  → confirmation-hub-workbench-tabs Wave 2 的「清单→E0-1 带入」读取（本 spec 保证这些列存在且持久化）

受限货币资金：
  E0-3「是否存在冻结担保或使用限制」列可筛选/汇总
  → 索引提示/跨底稿引用芯片指向 E1/附注（不自动写入）
```

### 关键决策

**决策 1：审定 E0.yaml 的四清单 sheet 列定义（`generated/` 提升为已审定，非另起真源）**

`d-form-table` 消费 render schema 的 `dynamic_table.columns`。最小侵入 = 直接把 E0.yaml 四清单 sheet 的 `columns` 从 `col_a` 占位改为源模板真实字段（`field` = 业务 snake_case、`label` = 源模板列名、加 `type`/枚举/日期/金额语义）。**不新建第二套渲染真源**（避免与 schema 消费链分叉）。

**决策 2：防重生成覆盖 —— sheet 级 `_reviewed: true` 标记 + 生成器尊重**

`generate_wp_render_schema.py` 重新生成会覆盖审定结果（Requirement 2.2）。方案：审定后的 sheet 加 `_reviewed: true`（+ `_reviewed_at`）；`generate_wp_render_schema.py` 生成时**跳过已标 `_reviewed: true` 的 sheet**（保留其人工审定 columns），只更新未审定 sheet。守卫测试：若生成器覆盖了 `_reviewed` sheet 的 columns → 失败（Requirement 7.4）。

**决策 3：不影响其他底稿 —— 只改 E0.yaml，`_reviewed` 机制通用但只对 E0 四 sheet 生效**

E0.yaml 是 E0 专属文件（`wp_code: E0`），改它不碰其他底稿的 schema（Requirement 2.4）。`_reviewed` 跳过机制加到生成器是通用的，但本 spec 只审定 E0 四清单 sheet。

**决策 4：清单列驱动上游带入（本 spec 只保证列存在可读）**

E0-3 落 `是否函证`（枚举点选）+ 开户银行（作被询证单位）/银行账号/币种/账户余额（原币）/账户类型（品种）等；E0-4 落 借款人/借款账号/余额/借款类型 等。Confirm_Flag + 这些字段是「清单→E0-1 带入」（归 confirmation-hub-workbench-tabs Wave 2）的数据来源。本 spec 保证列存在 + 持久化 + 刷新回显（Requirement 3.1）；带入逻辑本身不在本 spec。

**决策 5：受限货币资金只提示不写入**

E0-3「是否存在冻结担保或使用限制」枚举列可筛选/汇总；受限行提供索引提示或跨底稿引用芯片指向 E1/附注，**不自动写入其他底稿**（Requirement 4.2）；源模板无受限金额列则不加金额列（Requirement 4.3）。

**决策 6：四表取数为可选增强，无账户级维度不臆造**

`tb_aux_balance` 若有开户行/账号维度 MAY 提供「从余额表带入清单」（去重、不覆盖手工、标来源）；无账户级维度（只有科目级总额）则不臆造账户明细、明示手工录入（Requirement 5.3）。本项可选，非四清单落列的前置。

## Components and Interfaces

### 改造

| 文件 | 动作 |
|---|---|
| `backend/data/ledger_adapters/wp_render_schema/generated/E0.yaml` | 四清单 sheet 的 `dynamic_table.columns` 从 `col_*` 占位改为源模板真实字段 + `_reviewed: true` 标记 |
| `backend/scripts/generate_wp_render_schema.py` | 生成时跳过 `_reviewed: true` 的 sheet（保留人工审定 columns） |

### 新增

| 文件 | 职责 |
|---|---|
| `e0SendListSourceManifest`（数据文件，前端或后端 data） | 四清单 sheet 源模板真实列清单（契约守卫基准） |

### 不改

`confirmation-summary` / confirmation-v1 / 后端 render 调度 / E0 其他 sheet / 其他底稿的 render schema。

## Data Models

### E0-3 货币资金发函记录表（源模板列，M0 逐列核对定稿）

| field (snake_case) | label（源模板） | type/枚举 |
|---|---|---|
| `account_subject` | 所属科目 | text |
| `bank_name` | 开户银行 | text（作被询证单位）|
| `is_confirm` | 是否函证 | select 是/否 |
| `account_holder` | 账户名称 | text |
| `bank_account` | 银行账号 | text |
| `currency` | 币种 | text |
| `interest_rate` | 利率 | number（scale 明确）|
| `account_type` | 账户类型 | select |
| `balance_orig` | 账户余额（原币）| amount |
| `is_pooling` | 是否资金归集 | select 是/否 |
| `period_range` | 起止日期 | date range |
| `has_restriction` | 是否存在冻结担保或使用限制 | select 是/否 |
| `remark` | 备注 | text |

### E0-4 借款发函记录表

| field | label | type |
|---|---|---|
| `borrower` | 借款人 | text |
| `loan_account` | 借款账号 | text |
| `balance` | 余额 | amount |
| `loan_date` | 借款日期 | date |
| `maturity_date` | 到期日 | date |
| `interest_rate` | 利率 | number |
| `guarantor` | 抵质押品担保人 | text |
| `loan_type` | 借款类型 | select |
| `accrued_interest` | 期末应付利息 | amount |

> E0-5（应付银行承兑汇票）/ E0-6（理财产品）列在 M0 逐列核对源模板后补全（本 design 不臆造未实测的两张列）。

## Correctness Properties

### Property 1: 四清单渲染列 == 源模板清单
E0-3/E0-4/E0-5/E0-6 渲染列 SHALL 与 `e0SendListSourceManifest` 一致（列名与顺序），SHALL NOT 含 `col_*` 占位字段。
**Validates: Requirements 1.1, 1.2, 7.1**

### Property 2: 枚举/日期/金额列语义正确
是否函证/账户类型/是否资金归集/是否存在限制/借款类型 SHALL 为点选；起止日期/借款日期/到期日 SHALL 为日期控件；金额/利率 SHALL 按平台数值格式右对齐。
**Validates: Requirements 1.3, 1.4, 1.5**

### Property 3: `_reviewed` 防覆盖
`generate_wp_render_schema.py` 重新生成 E0.yaml 时 SHALL 跳过 `_reviewed: true` 的四清单 sheet，其审定 columns SHALL 逐字不变。
**Validates: Requirements 2.1, 2.2, 7.4**

### Property 4: 不影响其他底稿
本 spec 改动后其他底稿走 `d-form-table` 的渲染列 SHALL 逐字不变（只改 E0.yaml）。
**Validates: Requirements 2.4, 6.2**

### Property 5: Confirm_Flag 持久化 + 上游字段可读
`is_confirm` SHALL 持久化并刷新回显；带入 E0-1 所需字段（开户银行/借款人、账号、币种、余额、品种）SHALL 在清单可读。
**Validates: Requirements 3.1, 3.2, 3.3**

### Property 6: 受限行可识别 + 不自动写入
`has_restriction='是'` 行 SHALL 可筛选/汇总；SHALL 提供索引提示或引用芯片，SHALL NOT 自动写入其他底稿；源模板无受限金额列 SHALL NOT 新增金额列。
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 7: 既有数据回显不丢
E0 四清单既有已录数据 SHALL 可回显或有明确迁移路径，SHALL NOT 静默丢弃。
**Validates: Requirements 6.1**

### Property 8: 四表取数不臆造
无账户级维度时 SHALL NOT 臆造账户明细；带入 SHALL 去重且不覆盖手工行 + 标来源。
**Validates: Requirements 5.2, 5.3, 5.4**

## Error Handling

| 场景 | 处理 |
|---|---|
| E0.yaml 被重新生成 | `_reviewed: true` sheet 被跳过，审定 columns 保留；否则守卫失败 |
| 旧占位数据（col_a 键）| 迁移映射到真实 field 或明示需重录（不静默丢） |
| 四表无账户级维度 | 不臆造，明示手工录入 |
| 受限货币资金披露承载不明 | 只提示/引用芯片，不自动写 E1/附注 |

## Testing Strategy

- **契约测试**：Property 1 四清单列对 manifest、Property 3 `_reviewed` 防覆盖（模拟生成器跑一遍断言 columns 不变）
- **属性测试**：Property 5 Confirm_Flag 候选去重（`是否函证=是` 才进候选）、Property 7 round-trip 回显
- **单元测试**：Property 2 枚举/日期/金额语义、Property 6 受限行识别+不写入、Property 8 四表取数不臆造
- **零回归门**：函证域测试 + render schema 相关测试全绿；其他底稿 `d-form-table` 渲染不变；后端 `get_diagnostics`/`py_compile` OK
- **Playwright**：E0-3（是否函证+受限列+日期/金额控件）、E0-4（借款清单）渲染验证；旧数据回显不丢

## Migration / Phasing

| 阶段 | 内容 | 可回退 |
|---|---|---|
| **M0** | E0-3/E0-4/E0-5/E0-6 逐列核对源模板 → `e0SendListSourceManifest` + 既有 E0 清单数据核实（纯只读+数据文件） | 无风险 |
| **M1** | E0.yaml 四清单 sheet columns 审定（col_* → 真实 field/label/type）+ `_reviewed` 标记 | 单文件可回退 |
| **M2** | `generate_wp_render_schema.py` 尊重 `_reviewed` 跳过机制 | 可回退 |
| **M3** | 受限货币资金识别/引用芯片 + 四表取数（可选增强） | 独立可回退 |
| **M4** | 契约/属性/守卫 + 零回归门 + Playwright | 仅测试 |

**M0 硬前置**：四清单源模板列未逐列核对不得进 M1（避免臆造/漏列）。四表取数（M3）为可选增强，非四清单落列前置。
