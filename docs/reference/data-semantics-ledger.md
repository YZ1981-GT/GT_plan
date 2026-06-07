# 数据口径账

> 登记平台中金额、年度、准则、状态等数据语义的统一口径。新增金额字段必须声明 Decimal 序列化方式。

## 使用说明

- 新增金额字段的 PR 必须说明单位（元/万元）和 Decimal 精度
- 新增状态字段的 PR 必须说明是否进入枚举字典
- stale 规则记录数据新鲜度判定逻辑
- 数据来源记录字段的权威源表

## 金额口径

| # | 字段/概念 | 单位 | 精度 | Decimal 方式 | 来源表 | 说明 |
|---|----------|------|------|-------------|--------|------|
| 1 | trial_balance.audited_amount | 元 | 2 位小数 | Numeric(18,2) | trial_balance | 审定数，报表主源 |
| 2 | trial_balance.unadjusted_amount | 元 | 2 位小数 | Numeric(18,2) | trial_balance | 未审数（导入原值） |
| 3 | trial_balance.aje_adjustment | 元 | 2 位小数 | Numeric(18,2) | trial_balance | 审计调整合计 |
| 4 | financial_report.current_period_amount | 元 | 2 位小数 | Numeric(18,2) | financial_report | 本期报表金额 |
| 5 | adjustment_entries.debit_amount / credit_amount | 元 | 2 位小数 | Numeric(18,2) | adjustment_entries | 调整分录借/贷 |
| 6 | tb_ledger.debit_amount / credit_amount | 元 | 2 位小数 | Numeric(18,2) | tb_ledger | 序时账借/贷（每行单边） |
| 7 | overall_materiality | 元 | 2 位小数 | Numeric(18,2) | projects（重要性） | 整体重要性水平 |
| 8 | consol_amount | 元 | 2 位小数 | = individual_sum + adjustment + elimination | 合并计算值 | 合并报表金额 |
| 9 | 前端显示金额 | 元 | 千分位 + 2 位小数 | `GtAmountCell` 组件 | — | 统一元为默认单位 |
| 10 | Excel 导入金额 | 元 | 保留原始精度 | Python Decimal | 导入文件 | 导入时不做单位转换 |

## 年度口径

| 概念 | 取值方式 | 说明 |
|------|---------|------|
| 审计年度 | `EXTRACT(YEAR FROM projects.audit_period_end)::int` | 非独立列，从审计期间结束日提取 |
| 会计期间 | `projects.audit_period_start` ~ `projects.audit_period_end` | 可能跨年 |
| 比较年度 | 当前审计年度 - 1 | 用于报表比较列 |

## 准则口径

| 准则类型 | 枚举值 | 影响模块 |
|---------|--------|---------|
| 企业会计准则 | `CAS` | 报表模板、附注模板、科目映射 |
| 小企业会计准则 | `SMALL_ENTERPRISE` | 报表模板简化版 |
| 政府会计准则 | `GOV` | 政府报表模板 |

## 状态口径

| # | 状态域 | 枚举名 | 典型值 | 是否进字典 | 来源 |
|---|--------|--------|--------|----------|------|
| 1 | 项目状态 | ProjectStatus | draft/in_progress/completed/archived | ✅ | system_dicts |
| 2 | 底稿状态 | WorkpaperStatus | not_started/in_progress/review/approved | ✅ | system_dicts |
| 3 | 调整状态 | AdjustmentReviewStatus | pending/approved/rejected | ✅ | system_dicts |
| 4 | 复核状态 | ReviewStatus | pending/in_review/approved/rejected | ✅ | system_dicts |
| 5 | 导入任务状态 | ImportJobStatus | queued/running/completed/failed | ❌ 内部 | import_jobs |

## Stale（数据新鲜度）规则

| 数据对象 | 触发 stale 条件 | 刷新方式 | 服务 |
|---------|----------------|---------|------|
| 报表金额 | TB 变更 / 调整变更 | 重新聚合 | `stale_summary_service` |
| 附注数据 | 报表行变更 / TB 变更 | 事件级联 | `event_handlers` |
| 合并数据 | 子企业 TB 变更 | cascade refresh | `consol_cascade_refresh_service` |
| 公式快照 | 源数据变更 | snapshot_writer 重算 | `custom_query/snapshot_writer` |

## 铁律

1. **报表金额统一以"元"为默认单位**（不默认万元）
2. **前端 `GtAmountCell` 统一展示**，禁止裸数字直接渲染
3. **Python 后端金额用 `Decimal`**，禁止 `float`（有 `check_no_float_amount.py` 守护）
4. **导入不做单位转换**，保留原始精度

## 变更记录

| 日期 | 变更人 | 内容 |
|------|--------|------|
| 2026-06-06 | 初始化 | 创建账本骨架，登记 10 条金额口径 + 状态/年度/准则/stale 规则 |
