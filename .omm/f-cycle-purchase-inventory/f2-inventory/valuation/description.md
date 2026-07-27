# F2 计价与减值（`f2-inventory-valuation-impairment`）

主入口 `GtF2InventoryValuation.vue`，后端 `_f2_inventory_valuation_impairment.py`。
解决**计价准确性**与**跌价（可变现净值）**两个认定，是 F2 四组里业务最重的一组。

## 计价测试

- `F2TabValuationFifo`（先进先出）/ `F2TabValuationAvg`（移动加权平均）
- `F2ValuationTestSheet` / `F2ValuationDateSheet` / `F2ValuationMonthlySheet`（按日 / 按月计价测试表）
- `F2TabStandardCostTest` + `F2StdCostMonthlySheet`（标准成本法及差异分摊）

## 成本归集

- `F2TabProductionCostDetail`（生产成本明细）
- `F2TabOverheadDetail`（制造费用明细）
- `F2TabDirectLaborAnalysis` + `F2LaborMatrixTable`（直接人工分析）
- `F2TabCostAllocation`（成本分配）

## 采购与领用检查（凭证级 + 引导弹窗）

| 表 | 引导弹窗 | 要点 |
|---|---|---|
| `F2TabPurchaseInboundCheck` | `F2PurchaseVoucherDialog` | 20+ 列五类单据：记账凭证 / 入库验收 / 质检 / 物流 / 采购发票；5 分组卡片 + 每组 📎OCR 只回填本组字段 + 实时勾稽（账数量↔入库/发票数量、账金额↔发票金额、有账无入库单） |
| `F2TabMaterialUsageCheck` | `F2MaterialUsageVoucherDialog` | 材料领用 |
| `F2TabSubcontractCheck` | `F2SubcontractVoucherDialog` | 委外加工；**表三计价勾稽**：收回材料成本 ≈ 发出材料成本 + 加工费（CAS 存货成本恒等），状态分 一致 / 未全额收回 / 计价差异 / 待填 |
| `F2TabRelatedPurchase` | — | 关联采购定价 |

## 跌价与呆滞

- `F2TabImpairmentTest`（跌价测试：成本 vs 可变现净值孰低）
- `F2TabImpairmentReversal`（跌价转回）
- `F2TabObsoleteInventory`（呆滞存货）

跌价结论 → 科目 1471 → F2 审定表跌价组（`sumImpairmentAjeByRowKey` 把 F2-14 的 AJE 汇总为跌价准备账项调整）。

## 引导弹窗范式（F2 是发源地）

一笔业务一张卡：分组卡片对齐源模板的单据分组 + 每组 📎上传→OCR **只回填本组字段** +
右侧实时勾稽面板（红黄提示）+ 确认后回写主表。主表保留"完整表格"视图供批量填 / 抽凭批量回填 / 导入导出，
**两条路并存共用同一行模型与同一套异常判定函数**（不分叉）。
