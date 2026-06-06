# 数据口径账

> 登记平台核心业务数据的语义口径、单位、来源规则。避免前后端、报表、穿透之间口径不一致。

## 登记规则

- 新增金额字段必须声明单位（元/万元）和序列化方式（Decimal/float）
- 新增年度/期间字段必须声明取值来源
- stale 状态必须声明失效条件和刷新触发
- 枚举状态必须进字典（不可硬编码字符串）

## 数据口径登记表

| 数据项 | 字段/来源 | 单位/类型 | 口径说明 | 注意事项 |
|--------|-----------|-----------|----------|----------|
| 报表行金额 | `financial_report.current_period_amount` | 元 / Decimal | 当期金额，含调整 | 统一元，禁万元 |
| 试算余额 | `trial_balance.audited_amount` | 元 / Decimal | 审定数=未审数+AJE+RJE | 报表穿透源 |
| 期初余额 | `trial_balance.opening_balance` | 元 / Decimal | 上年审定结转 | 可能为空 |
| AJE 调整 | `trial_balance.aje_adjustment` | 元 / Decimal | 审计调整分录合计 | 正=借方增 |
| 年度 | `route.query.year` / `EXTRACT(YEAR FROM audit_period_end)` | 整数 | 审计期间终止年份 | projects 表无 year 列 |
| 准则 | `project.accounting_standard` | 枚举 | CAS/IFRS/ASBE 等 | 关联报表格式 |
| 底稿状态 | `working_paper.status` | 枚举 | draft→reviewed→signed_off | 走 gate 规则 |
| stale 标记 | `wp_index.is_stale` | bool | TB 变更后底稿过期 | 触发=TB 重导/AJE 变更 |
| 科目编码 | `trial_balance.standard_account_code` | varchar | 标准科目表编码 | 非 account_code |
| 调整分录号 | `adjustments.adjustment_no` | varchar | AJE-001 格式 | 项目内唯一 |

## 易混淆口径对照

| 容易搞混的 | 正确用法 | 错误用法 |
|------------|----------|----------|
| 报表金额单位 | 始终"元" | ~~万元~~（历史遗留已清） |
| 科目编码列 | `standard_account_code` | ~~account_code~~（已废弃） |
| 穿透源 | `trial_balance.audited_amount` | ~~tb_balance.closing_balance~~（导入原始值） |

## 变更历史

| 日期 | 变更 | PR |
|------|------|----|
| 2025-01-01 | 初始骨架创建 | — |
