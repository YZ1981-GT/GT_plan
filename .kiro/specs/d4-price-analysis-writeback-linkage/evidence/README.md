# D4 价格分析联动证据

## 单元 / 接线守卫（本轮已绿）

- `d4AdjudicationRowLinkage.spec.ts` — D4-2/3 → D4-1 computed 派生
- `d4PriceUpstreamImport.spec.ts` — D4-10/11 上游导入 merge
- `d4PriceWritebackLinkage.spec.ts` — `d4:price-abnormal` 接收端
- `d4NoDeadEvent.spec.ts` / `d4PriceHostWiring.spec.ts` — 无死事件 + 宿主 provide
- `d4PriceAbnormalVisibility.spec.ts` — D4-2 保留并暴露 `priceAbnormal`
- `useD4FormulaEngine.spec.ts` — WP 解析 + 预设/覆盖 + 未审合计
- `backend/tests/test_d4_price_import_formula_preserve.py` — 导入 merge + 公式元数据副表往返

## 真栈 Playwright

- Spec：`audit-platform/frontend/e2e/g5-1-d4-price-linkage.spec.ts`
- 默认 `test.skip`（需 `RUN_FULL_E2E=1`）
- 跑通后落本目录 `network-and-ui.json`

## 公式真源

- D4-10 `totalAmount` preset = `WP('D4-2','本期未审合计')`（`D4_10_TOTAL_AMOUNT_PRESET`）
- 取值走 `mainRevenueUnadjustedTotal`（未审 Σ months），手工覆盖 +「恢复公式」
- 导入导出：`merge_d4_10_import_rows` + 导出「公式元数据」sheet
