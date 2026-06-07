# 设计文档：账表导入符号约定与历史迁移

## 概述

本设计把借贷方向和金额符号从前端推断下沉到导入与存储层。核心是新增方向来源字段、结构化 converter 输出、历史 dry-run 迁移和试算表展示改造。

## 核心设计

### 1. 数据模型扩展

`tb_balance` / `tb_aux_balance` 建议新增字段：

| 字段 | 说明 |
|---|---|
| `opening_direction` | 期初方向：debit / credit / unknown |
| `closing_direction` | 期末方向：debit / credit / unknown |
| `opening_direction_source` | 期初方向来源 |
| `closing_direction_source` | 期末方向来源 |
| `sign_convention_version` | 符号约定版本，如 `v1_net_debit_positive` |
| `sign_anomaly_flags` | JSONB，记录方向异常、借贷并存、类别冲突 |
| `direction_review_status` | pending / accepted / corrected |
| `direction_override_reason` | 用户覆盖原因 |
| `direction_overridden_by` / `direction_overridden_at` | 留痕 |

`tb_ledger` / `tb_aux_ledger` 可新增：

| 字段 | 说明 |
|---|---|
| `entry_direction` | debit / credit / both / unknown |
| `entry_direction_source` | split_columns / explicit_direction / inferred |

用户覆盖建议使用独立 overlay 表，而不是直接改写四表原始导入行：

| 字段 | 说明 |
|---|---|
| `project_id` / `dataset_id` | 项目和数据集 |
| `table_name` | tb_balance / tb_aux_balance / trial_balance |
| `row_id` 或 `account_code` | 覆盖目标 |
| `period_field` | opening / closing / entry |
| `override_direction` | debit / credit |
| `original_direction` / `original_direction_source` | 覆盖前方向与来源 |
| `reason` | 用户覆盖原因 |
| `overridden_by` / `overridden_at` | 留痕 |

读模型按"原始导入行 + overlay"合成展示，避免覆盖抹除原始事实。

### 2. DirectionSource 枚举

```python
DirectionSource = Literal[
    "explicit_direction",
    "split_columns",
    "account_category_inferred",
    "account_category_inferred_low_confidence",
    "user_override",
    "legacy_inferred",
    "unknown",
]
```

前后端共享枚举，试算表用该枚举显示方向来源。

### 3. Converter 结果

`convert_balance_rows()` 从返回 tuple 改为返回 `BalanceConversionResult`，迁移期可保留兼容包装函数。

```python
class BalanceConversionResult(BaseModel):
    balance_rows: list[dict]
    aux_balance_rows: list[dict]
    warnings: list[ConversionWarning]
    sign_anomalies: list[SignAnomaly]
    stats: dict
```

`pipeline.py` 读取 `result.balance_rows` / `result.aux_balance_rows`，并把 warnings 合并进 `all_findings` 或 job result summary。

### 4. 方向推导规则

优先级：

1. 显式方向列：`direction` / `opening_direction` / `closing_direction`
2. 借贷分列：`opening_debit - opening_credit`、`closing_debit - closing_credit`
3. 类别推断：Account_Category + Contra_Asset
4. 历史 fallback：旧数据无字段时由试算表或服务标记 `legacy_inferred`

借贷分列规则：

- 仅借方非零：方向 debit
- 仅贷方非零：方向 credit
- 两方同时非零：按净额符号判定，并记录 `both_debit_credit_nonzero`
- 两方均空或 0：方向 unknown，金额为 0 或 NULL

源分列字段保持源文件绝对值，不做符号反转：

```text
opening_debit/opening_credit/closing_debit/closing_credit = 源分列绝对值
opening_balance/closing_balance = 借方列 - 贷方列 后的带符号净额
```

### 5. Account_Category 获取

Converter 保持纯函数，因此类别推断所需的 account metadata 由 pipeline 在调用 converter 前注入：

```python
convert_balance_rows(cleaned_rows, account_meta_by_code=...)
```

`account_meta_by_code` 来源可以是 `account_chart`、标准科目表或项目已有 mapping。缺失 metadata 时不强行推断，标记 `unknown`。

当 metadata 缺失但科目编码前缀足够明确时，可生成低置信推断：

- 1xxx：asset
- 2xxx：liability
- 3xxx / 4xxx：equity 或成本/权益混用，默认低置信
- 5xxx / 6xxx：pnl，需结合科目名称进一步判断

低置信推断只能用于展示 fallback 和诊断提示，不得作为自动改写历史金额的依据。

### 6. 历史迁移

迁移分两层：

1. DDL 迁移：新增方向字段和索引，幂等。
2. 数据校正脚本：先 dry-run 生成报告，再按确认清单执行。

dry-run 输出建议：

```json
{
  "project_id": "...",
  "dataset_id": "...",
  "account_code": "2221",
  "account_name": "应交税费",
  "old_closing_balance": "14203492.00",
  "suggested_closing_balance": "-14203492.00",
  "reason": "liability_normal_credit",
  "risk": "manual_review_required"
}
```

冲突项默认不自动改写，除非用户确认或脚本传入明确 allowlist。

### 6.1 迁移安全等级

| 等级 | 自动改写 | 说明 |
|---|---|---|
| `safe_auto_fix` | 可进入 allowlist 自动修 | 源文件存在显式方向或借贷分列证据，且当前存储符号与证据矛盾 |
| `manual_review_required` | 不自动改写 | 只有科目类别/编码前缀推断，或业务含义可能为反向余额 |
| `no_change` | 不改写 | 数据已符合约定，或反向余额被判断为可能真实业务余额 |

例如 2221 应交税费正数不能仅凭"负债类正常贷方"直接改为负数；它可能是留抵、重分类或导入错误，必须结合源方向证据或进入人工复核。

### 7. 试算表展示

后端试算表 API 返回：

```typescript
interface TrialBalanceRow {
  direction?: 'debit' | 'credit' | 'unknown'
  direction_source?: DirectionSource
  direction_review_status?: string
  sign_anomaly_flags?: Record<string, unknown>
}
```

`TrialBalance.vue#getDirection()` 改为：

1. 用户持久化覆盖方向
2. 后端权威方向
3. 历史 fallback 类别推断，并显示 `legacy_inferred`

前端点击切换方向时调用后端接口，记录原因后再更新 UI。

## 迁移兼容

- 新字段可为空，旧数据继续可读。
- 旧 converter tuple 返回可用兼容 wrapper 过渡一个版本。
- 旧前端无方向字段时 fallback，但必须显示风险标记。

## 测试策略

- converter 单元测试覆盖三类方向来源和异常。
- migration dry-run 测试覆盖幂等、冲突不改写、allowlist 改写。
- API 测试覆盖试算表方向字段返回。
- Vitest 覆盖 `TrialBalance.vue` 不再默认按金额正负判断普通科目方向。
