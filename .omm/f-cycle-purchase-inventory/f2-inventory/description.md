# F2 存货（1401~1411 原值 / 1412 进销差价 / 1471 跌价准备）

**四个 componentType、七个前端子目录**，是全平台最大的科目包。四个入口共享 `f2AccountModel.ts` 科目模型与审定表口径。

## 四个入口

| componentType | 主入口 | 覆盖 |
|---|---|---|
| `f2-inventory-main` | `GtF2InventoryMain.vue` | core / detail / analysis |
| `f2-inventory-valuation-impairment` | `GtF2InventoryValuation.vue` | valuation |
| `f2-inventory-special` | `GtF2InventorySpecial.vue` | f2-special（contract + ipo） |
| `f2-stocktake-bundle` | `GtF2StocktakeBundle.vue` | stocktake |

## 七个子目录（`f2/`）

| 目录 | 组件 |
|---|---|
| `core/` | `F2TabAdjudication` + `F2AdjudicationBlockTable`（分块审定表）/ `F2TabAdjustment` / `F2TabDetailSummary` / `F2TabProcedure` / `F2TabDisclosureListed` / `F2TabDisclosureSoe` |
| `detail/` | `F2DetailSheet`（配置驱动 `f2DetailSheetConfigs.ts`）+ 变体：`Bio`（生物资产）`ContractPerf`（合同履约）`Dev`/`DevCost`（开发成本）`Outsourced`（委外）`Turnover`（周转材料，含 `TurnoverLinesTable`） |
| `analysis/` | `F2TabOverallAnalysis` / `F2TabProductionSales`（产销量）/ `F2TabCostComparison` / `F2TabPolicy` |
| `valuation/` | 见 `valuation/` 元素 |
| `stocktake/` | 见 `stocktake/` 元素 |
| `inspection/` | `F2CutoffSheet` + `f2CutoffSheetConfigs.ts` + `F2CutoffOverviewCard` + `F2CutoffVoucherDialog`（截止测试，配置驱动多 sheet） |
| `shared/` | `F2SheetToolbar`（统一工具栏）`F2ReviewChip` |

## 配置驱动是 F2 的核心手法

`f2DetailSheetConfigs.ts` / `f2CutoffSheetConfigs.ts` / `f2StocktakeConfigs.ts` —— 同一个通用 Sheet 组件
按配置渲染多张源模板表，避免为每张表写一个组件。**改这类表优先改配置，不要新增组件**。

## 审定表的特殊结构

- **两个科目族分块**：原值组（gross，1401~1411）与跌价组（impairment，1471），`F2AdjudicationBlockTable` 分块渲染
- **账项调整是单列净额**（不是 AJE/RJE 双列），`updateCell(block, rowKey, field, value)` 四参 block-scoped
- **F2-14 overlay 优先**：`crossSheet.grossAdjustmentByRowKey` / `impairmentAdjustmentByRowKey` 覆盖手工值
- TB 回写科目参数化（按 rowKey → `F2_ROW_KEY_ACCOUNT` 映射逐科目回写）

## 附注

`五、9`（上市）/ `八、10`（国企），`buildF2SyncPayload` + columns（`_sub_table_columns`）已登记进覆盖率守卫。
