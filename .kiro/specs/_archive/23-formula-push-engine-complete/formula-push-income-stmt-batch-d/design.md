# 设计：公式推送批 D — 损益类审定表

> 细化 `formula-push-all-subjects-rollout` design §九中 4 条「审定数」列名改写。

## 一、损益类口径

损益类科目在 `trial_balance` 表中：
- `audited_amount` = 审定**发生额**（不是余额）
- `opening_balance` = 上年审定发生额（比较数）
- 本期发生额 = `audited_amount - opening_balance`

推送规则的表达式须使用 `TB(code,'本期发生额')`，context = `trial_balance_audited_occurrence`。

批 B 的 4 条锚点（D4-1 两条、H10、I6）原用 `TB(code,'审定数')`，须改写为：
- `TB(code,'本期发生额')` + `context.tb = trial_balance_audited_occurrence`
- 逐条现读审定表上的语义确认是期末发生额而非余额

## 二、实现选项

**选项 A**：在 `AdjudicationSpec` 加 `is_income_statement: bool`，影响：
- 审定合计公式用发生额而非余额
- 默认上下文改为 `trial_balance_audited_occurrence`

**选项 B**：独立 `IncomeStatementBinding` 族 binding

**建议选项 A**：损益类审定表与资产负债类结构一致（组合行 + 审定合计），只是取数列不同。

## 三、与批 B/C 的关系

- 批 B 的 4 条锚点在本批改写列名
- 批 C 的 `BalanceAdjudicationBinding` 在本批扩展 `is_income_statement` 支持
