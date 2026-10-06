# 需求：公式推送批 D — 损益类审定表

> 前置：批 C（资产负债类审定表族）canary 通过 + Task 8 发生额上下文已落地。
> 交叉引用：`formula-push-all-subjects-rollout` design §九（4 条「审定数」列名）。

## 1. 目标

接管损益类科目的审定表推送。损益类科目的「审定数」实际存的是**审定发生额**（`audited_amount - opening_balance`），需使用 `trial_balance_audited_occurrence` 上下文。

## 2. 范围

| # | 需求 | 验收标准 |
|---|------|----------|
| D1 | 损益类 binding 或规格扩展 | `BalanceAdjudicationBinding` 的 `is_income_statement=True` 变体或独立族 |
| D2 | 发生额口径 | 使用 `TB(code,'本期发生额')`，context=`trial_balance_audited_occurrence` |
| D3 | 逐科目声明 | D4/I6 等损益类科目规格现读确认 |
| D4 | D4 canary（可复用批 B canary） | 锚点值 = 发生额口径（非余额口径） |
| D5 | 与报表引擎逐值对拍 | `TB(code,'本期发生额')` 与 `ReportFormulaParser._resolve_tb(code,'本期发生额')` 逐 Decimal 相等 |
| D6 | 独占键 + 清册 | 生成器 `--check` 通过 |
| D7 | 损益类推送→利润表标 stale | 推送完成后按科目码映射到利润表行 `is_stale=True` |
| D8 | 发生额与利润表行逐值对拍 | 推送发生额 == `ReportFormulaParser._resolve_tb(code,'本期发生额')` |

## 3. 科目候选

- I6（无形资产摊销 / 处置损益）
- D4-1 两条锚点（已在批 B 列出，损益列名需改写）
- H10（资产处置收益）
- 其他从 `d_cycle_extraction_presets.json` 现扫含 `'审定数'` 列名的损益类条目

## 4. 不做

- 资产负债类审定表（已归批 C）
- 附注推送（归批 E）
