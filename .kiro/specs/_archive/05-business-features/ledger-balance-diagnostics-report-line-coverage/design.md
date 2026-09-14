# 设计文档：借贷不平衡诊断与报表行次覆盖治理

## 概述

本设计统一导入校验、试算表数据质量检查和报表行次映射之间的不平衡诊断。核心是新增 `BalanceDiagnosticsService` 和 `BalanceDiagnosticsDialog`，并补齐 seed 覆盖率治理脚本。

## 核心设计

### 1. `BalanceDiagnosticsResult`

```typescript
interface BalanceDiagnosticsResult {
  status: 'passed' | 'warning' | 'blocking'
  caliber: 'trial_balance_debit_credit' | 'ledger_debit_credit' | 'balance_vs_ledger' | 'balance_sheet_equation'
  difference: string
  debit_total?: string
  credit_total?: string
  asset_total?: string
  liability_equity_total?: string
  likely_causes: DiagnosticCause[]
  unmatched_accounts: UnmatchedAccount[]
  sign_anomalies: SignAnomalySummary[]
  top_contributors: DiagnosticContributor[]
  jump_targets: DiagnosticJumpTarget[]
}
```

`caliber` 是必填字段，前端必须展示其中文解释。

### 1.1 Caliber 数据源

| Caliber | 数据源 | 公式 / 口径 | top_contributors |
|---|---|---|---|
| `ledger_debit_credit` | `tb_ledger` | `SUM(debit_amount) == SUM(credit_amount)` | 按凭证号聚合差额最大的前 10 条 |
| `balance_vs_ledger` | `tb_balance` + `tb_ledger` | `closing_balance = opening_balance + SUM(debit_amount) - SUM(credit_amount)` | 差额最大的前 10 个科目 |
| `trial_balance_debit_credit` | `trial_balance` + 权威方向/方向来源 | 按方向汇总借方余额与贷方余额；历史数据用 `legacy_inferred` 标记 | 差额贡献最大的前 10 个科目 |
| `balance_sheet_equation` | `financial_report` BS 合计行 | `资产合计 = 负债和所有者权益合计`，仅报表生成后使用 | 差额相关的报表行次 |

`balance_sheet_equation` 不得替代通用试算平衡。损益未结转场景必须使用 `trial_balance_debit_credit` 或明确提示口径差异。

### 2. 原因模型

```typescript
interface DiagnosticCause {
  code:
    | 'report_line_unmatched'
    | 'sign_convention_anomaly'
    | 'pnl_not_closed_or_caliber_gap'
    | 'source_data_unbalanced'
    | 'manual_review_required'
  severity: 'info' | 'warning' | 'blocking'
  title: string
  evidence_count: number
  confidence: number
  message: string
}
```

原因按 confidence 和 severity 排序。自动判断不足时，加入 `manual_review_required`。

### 3. `BalanceDiagnosticsService`

服务职责：

1. 从 `validator.py` findings 转换诊断结果。
2. 从 `DataQualityService` 检查结果生成诊断结果。
3. 查询 `report_line_mapping` 和 seed，生成 `unmatched_accounts`。
4. 查询符号异常字段，生成 `sign_anomalies`。
5. 生成前端跳转目标。

该服务不直接修改数据，只返回诊断和跳转建议。

如果 `sign_anomaly_flags` 尚未迁移上线或字段为空，服务必须 graceful degrade：

```json
{
  "code": "sign_anomaly_unavailable",
  "severity": "info",
  "message": "方向异常字段尚不可用，本次诊断未纳入符号异常原因"
}
```

这类提示不阻断其他原因输出。

### 4. 跳转目标

```typescript
interface DiagnosticJumpTarget {
  target: 'report_line_mapping' | 'sign_anomaly_review' | 'ledger_penetration' | 'data_quality'
  label: string
  params: Record<string, string>
  transport: 'route_query' | 'dialog_prop' | 'event_payload'
}
```

报表行次未匹配的 target 固定为 `report_line_mapping`。导入列映射只用于源文件列识别问题，不用于需求 10 的报表行次修复。

ReportLineMapping 的推荐跳转参数：

```json
{
  "target": "report_line_mapping",
  "transport": "dialog_prop",
  "params": {
    "account_code": "2701",
    "standard_account_code": "2701",
    "highlight": "true"
  }
}
```

### 5. 前端复用

新增 `BalanceDiagnosticsDialog.vue`，在以下入口复用：

- 导入失败 / 导入完成但有 blocking findings
- `DiagnosticPanel.vue` 中点击 `BALANCE_UNBALANCED`
- `DataQualityDialog.vue` 中点击借贷平衡检查详情
- `TrialBalance.vue` 的数据质量检查按钮

### 6. DataQualityService 口径拆分

`DataQualityService` 保留现有 checks，但调整语义：

- `ledger_debit_credit_balance`：基于 `tb_ledger` 借贷发生额
- `trial_balance_debit_credit`：基于试算表方向与带符号余额
- `balance_vs_ledger`：期末 = 期初 + 借 - 贷
- `report_balance`：资产负债表生成后的资产 = 负债 + 权益

`report_balance` 不再被描述为通用试算平衡。

### 7. Seed 覆盖率脚本

新增脚本建议：

```text
backend/scripts/check/check_account_to_report_line_seed_coverage.py
```

输出：

- 每个 Seed_Dimension 的映射数量和覆盖率
- 未覆盖标准科目
- 重复 `standard_account_code`
- 不存在的 `report_line_code`
- 非法 `report_type`
- 国企 / 上市同科目差异列表
- consolidated / standalone 差异列表

标准科目全集来源优先级：

1. 平台标准 AccountChart seed / CAS 标准科目库
2. 项目初始化时生成的标准科目表
3. 已确认的标准科目扩展 seed

报表模板行次只能用于校验 `report_line_code` 是否存在，不能反推出标准科目全集。

脚本首次进入 CI 前应生成 baseline：

```json
{
  "dimension": "soe_standalone",
  "known_missing_accounts": ["2701"],
  "generated_at": "2026-06-07"
}
```

CI 初期只阻断本次新增缺口；历史缺口在 P1/P2 阶段逐步清零。

### 8. 一键预设未匹配治理

`report_line_mapping_service.ai_suggest_mappings()` 或一键预设流程应返回：

```json
{
  "suggested_count": 120,
  "unmatched_accounts": [
    {"account_code": "2701", "account_name": "长期应付款", "amount": "1000.00", "reason": "seed_missing"}
  ]
}
```

前端展示未匹配清单，并允许进入手工映射。

### 9. Top contributors

`top_contributors` 按 caliber 使用不同来源：

- `ledger_debit_credit`：`voucher_no` 聚合，字段包含 `voucher_no`、`debit_total`、`credit_total`、`difference`。
- `balance_vs_ledger`：`account_code` 聚合，字段包含 `opening_balance`、`ledger_debit`、`ledger_credit`、`closing_balance`、`expected_closing`、`difference`。
- `trial_balance_debit_credit`：`standard_account_code` 聚合，字段包含 `direction`、`amount`、`direction_source`、`difference_contribution`。
- `balance_sheet_equation`：报表行次，字段包含 `report_line_code`、`row_name`、`amount`。

## 兼容策略

- 旧 `DataQualityDialog` 可先消费适配后的 details，不必一次性替换所有 UI。
- `DiagnosticPanel.vue` 继续展示原 findings，但对平衡类 code 增加打开统一弹窗入口。
- seed 覆盖率脚本先 warning，再在 CI P1 阶段升级为阻断。

## 测试策略

- pytest：`BalanceDiagnosticsService` 对 validator findings 的转换。
- pytest：DataQualityService 四种口径输出正确。
- pytest：seed 覆盖率脚本能发现缺失、重复和非法行次。
- Vitest：BalanceDiagnosticsDialog 渲染原因、跳转和口径说明。
- UAT：未匹配科目从诊断弹窗跳转到 ReportLineMappingDialog 并高亮。
