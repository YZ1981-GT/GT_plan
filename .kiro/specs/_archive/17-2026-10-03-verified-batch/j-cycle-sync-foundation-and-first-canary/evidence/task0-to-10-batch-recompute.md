# J 循环 T0~T10 批量现算

**日期**：2026-09-27

```
============================================================
T0: 前置产物清点
============================================================
  test_task52: ✅ (177,651 B)
  mutate_task52: ✅ (82,897 B)
  j_deletion_plan: ✅ (35,593 B)
  render_schema_j1: ✅ (3,270 B)
  wp_guidance_J1: ✅ (1,273 B)
  wp_guidance_J2: 🔴 MISSING (0 B)

============================================================
T1: 模板 3 文件 sha256/size/sheets
============================================================
  J1 应付职工薪酬.xlsx: 196,750 B  sha256=a6100d91202f4d06  sheets=23
  J2 长期应付职工薪酬-设定受益计划净资产.xlsx: 107,237 B  sha256=b9a4d87c95d275d7  sheets=9
  J3 股份支付.xlsx: 50,195 B  sha256=72e026f43612ec6b  sheets=6

============================================================
T1: manifest J entry
============================================================
  manifest entries 总数: 155
  J 相关 xlsx entry 数: 2
    xlsx/j1/gt-j1-employee-compensation: capability=single_onlyoffice adapter_id=None independent=True parent=None
    xlsx/j1/inspection/j1-tab-general-check: capability=single_onlyoffice adapter_id=None independent=False parent=xlsx/j1/gt-j1-employee-compensation

============================================================
T2: 四类「查过且没有」
============================================================
  无 pilot: ✅ (J 命中 0)
  无 J0: ✅ (J0 文件 0)
  J 模板总数: 3

============================================================
T3: 零回归基线
============================================================
  契约目录文件数: 29
    _example.candidate.json
    b60.hour_budget.json
    d1.notes_receivable_detail.json
    d2.receivable_detail.json
    d3.prepaid_receipts_detail.json
    d4.revenue_detail.json
    d5.receivables_financing_detail.json
    d6.contract_assets_detail.json
    d7.contract_liabilities_detail.json
    e1.monetary_fund_detail.json
    f1.prepayment_detail.json
    f2.inventory_main.json
    f2.inventory_special.json
    f2.inventory_valuation.json
    f2.stocktake_bundle.json
    f3.notes_payable_detail.json
    f4.accounts_payable_detail.json
    f5.cost_of_sales_detail.json
    g2.interest_receivable_detail.json
    g7.soe_subsidiary_disclosure.json
    g9.other_noncurrent_detail.json
    h1.disposal_check.json
    h9.lease_liability_detail.json
    i1.intangible_assets_detail.json
    i2.development_expenditure_detail.json
    i3.goodwill_detail.json
    i4.long_term_prepaid_detail.json
    i5.other_noncurrent_assets_detail.json
    i6.research_development_expense_detail.json
  adapter_id 非 None 的 entry 数: 11
    xlsx/gt-d1-notes-receivable: d1.notes_receivable_detail
    xlsx/gt-d2-accounts-receivable: d2.receivable_detail
    xlsx/gt-d4-operating-revenue: d4.revenue_detail
    xlsx/gt-g7-long-term-equity-main: g7.soe_subsidiary_disclosure
    xlsx/gt-h1-fixed-assets: h1.disposal_check
    xlsx/gt-i1-intangible-assets: i1.intangible_assets_detail
    xlsx/gt-i2-development-expenditure: i2.development_expenditure_detail
    xlsx/gt-i3-goodwill: i3.goodwill_detail
    xlsx/gt-i4-long-term-prepaid: i4.long_term_prepaid_detail
    xlsx/gt-i5-other-noncurrent-assets: i5.other_noncurrent_assets_detail
    xlsx/gt-i6-research-development-expense: i6.research_development_expense_detail

============================================================
T5: 载体 — J1 宿主 grep
============================================================
  GtJ1EmployeeCompensation.vue: 259 行
    http import: 0
    apiProxy import: 0
    checklist_get: 1
    bridge: 0
    notice: 0
    publishToTb symbol: 0
    localStorage: 0
    el-segmented: 1
    isOoAvailable: 0
    仅结构化: 1

============================================================
T6: 六类端点字面量
============================================================
  J 域文件数: 49
  checklist-responses PUT: 13 文件
    j1\GtJ1EmployeeCompensation.vue
    j1\analysis\J1TabIndustryCompare.vue
    j1\core\J1TabAdjudication.vue
    j1\core\J1TabAdjustment.vue
    j1\core\J1TabDisclosureListed.vue
    j1\core\J1TabDisclosureSoe.vue
    j1\inspection\J1TabAccrualCheck.vue
    j1\inspection\J1TabAllocationCheck.vue
    j1\inspection\J1TabGeneralCheck.vue
    j1\inspection\J1TabNonMonetaryCheck.vue
    j1\inspection\J1TabSeveranceCheck.vue
    j2\GtJ2DefinedBenefitPlan.vue
    j3\core\J3TabDetail.vue
  publish-to-tb: 1 文件
    j1\core\J1TabAdjudication.vue
  disclosure-notes/sync: 4 文件
    j1\core\J1TabDisclosureListed.vue
    j1\core\J1TabDisclosureSoe.vue
    j2\J2TabDisclosureListed.vue
    j2\J2TabDisclosureSoe.vue
  events/publish: 0 文件
  cross-wp-references/batch: 0 文件
  ai/generate-text: 16 文件
    j1\analysis\J1TabIndustryCompare.vue
    j1\analysis\J1TabMonthlyAnalysis.vue
    j1\core\J1TabAdjudication.vue
    j1\core\J1TabAdjustment.vue
    j1\core\J1TabDetail.vue
    j1\core\J1TabDisclosureListed.vue
    j1\core\J1TabDisclosureSoe.vue
    j1\inspection\J1TabAccrualCheck.vue
    j1\inspection\J1TabAllocationCheck.vue
    j1\inspection\J1TabGeneralCheck.vue
    j1\inspection\J1TabNonMonetaryCheck.vue
    j1\inspection\J1TabSeveranceCheck.vue
    j2\J2RuntimeMigration.unit.test.ts
    j3\core\J3TabCheck.vue
    j3\core\J3TabDetail.vue
    j3\core\J3TabIpoFocus.vue

  publishToTb 符号名全 J 域: 0
  publish-to-tb 端点全 J 域: 2

============================================================
T7: J1 owner 常量
============================================================

============================================================
T9: removeRow 签名
============================================================
  j1\core\J1TabAdjudication.vue#L576: function removeRow(id: string) {
  j1\core\J1TabAdjustment.vue#L111: function removeRow(rowId: string) {
  j1\core\J1TabDisclosureListed.vue#L478: function removeRow(id: string, category: string) {
  j1\core\J1TabDisclosureSoe.vue#L447: function removeRow(id: string, category: string) {
  j1\inspection\J1TabGeneralCheck.vue#L370: function removeRow(key: 'credit' | 'debit' | 'post', id: string) {
  j1\inspection\J1TabNonMonetaryCheck.vue#L223: function removeRow(id: string) { rows.value = rows.value.filter(r => r.id !== id); persist() }
  j1\inspection\J1TabSeveranceCheck.vue#L282: function removeRow(id: string) { rows.value = rows.value.filter(r => r.id !== id); persist() }
```
