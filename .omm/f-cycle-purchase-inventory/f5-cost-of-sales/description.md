# F5 营业成本（6401）

componentType `f5-cost-of-sales`，主入口 `GtF5CostOfSales.vue`，后端 `_f5_cost_of_sales.py`。
**损益类，取发生额**（`useF5Adjudication` 判定 `code.startsWith('6401') || 名称含营业成本/主营业务成本`）。

## Tab 组成（`f5/`）

| 组件 | 作用 |
|---|---|
| `F5TabAdjudication` | 审定表（未审/调整/审定），TB 6401 核对与回写 |
| `F5TabMonthlyDetail` | 月度明细（1–12 月成本构成） |
| `F5TabAdjustment` | 调整分录 |
| `F5TabComparison` | 成本对比分析（同比/结构） |
| `F5TabCostRollforward` | 成本倒轧（期初存货 + 本期购入/生产 − 期末存货 = 本期成本） |
| `F5TabQuantityRecon` | 量差调节（产销量与成本量的勾稽） |
| `F5TabMajorAdjustment` | 重大成本调整专项（接抽凭引擎） |
| `F5TabOtherCost` | 其他业务成本 |

## 关键机制

- **回写**：`useF5CosSalFormData.writebackTrialBalance(accountCode, auditedAmount)` → `PUT /trial-balance/writeback`；
  `useF5Adjudication` 发 `substantive:adjudicated`（`wpCode:'F5'` / `accountCode:'6401'`）+ `window` 的 `f5:writeback-trial-balance`
- **跨表引擎**：`useF5CrossSheet` 计算毛利率（与 D4 收入联动，`pullD4Revenue` 跨底稿取审定收入）、
  TB 核对、F5-2 月度 ↔ F5-1 勾稽、F5-7 倒轧 ↔ F5-1 勾稽，并在主入口汇总为全局告警条
- **后端 resolver**：`f5_ledger_monthly_by_product`（`@auto_resolver`，从 `tb_ledger` 6401 按产品 × 月汇总借方净额），
  供 F5-2 从序时账导入
- **project_context**：render 提供 `client_name` / `audit_year` / `bs_date` / `related_parties` / `tb_amount`(6401 未审/审定)

## 与其他循环的关系

- **F5 ↔ D4 毛利率**：营业成本与营业收入配比，毛利率异常是核心分析性程序信号
- **F5 ↔ F2 存货**：倒轧关系（期初 + 购入/生产 − 期末 = 成本），存货计价方法直接决定成本结转
- **F5 ↔ F2 采购**：采购价格/单位耗用异常传导到成本
- 损益类不进资产负债表，审定数进利润表 IS 行
