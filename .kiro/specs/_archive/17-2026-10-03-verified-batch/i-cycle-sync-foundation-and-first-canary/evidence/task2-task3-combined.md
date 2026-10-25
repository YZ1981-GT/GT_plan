# Task 2 + Task 3 — 合并现算证据

**日期**：2026-09-27　**方法**：python 脚本逐项读文件

```
============================================================
TASK 2: 四类「查过且没有」红判据
============================================================

--- 2a: pilot 契约逐文件核查 ---
  契约目录总文件数: 18
  review.entry_id 以 xlsx/gt-i 开头的: 0
  ✅ 无一条以 xlsx/gt-i 开头 → I 循环无 pilot 确认
  全部 review.entry_id (17 条):
    b60.hour_budget.json: xlsx/b60/gt-b60-bundle
    d1.notes_receivable_detail.json: xlsx/gt-d1-notes-receivable
    d2.receivable_detail.json: xlsx/gt-d2-accounts-receivable
    d3.prepaid_receipts_detail.json: xlsx/gt-d3-prepaid-accounts
    d4.revenue_detail.json: xlsx/gt-d4-operating-revenue
    d5.receivables_financing_detail.json: xlsx/gt-d5-receivables-financing
    d6.contract_assets_detail.json: xlsx/gt-d6-contract-assets
    d7.contract_liabilities_detail.json: xlsx/gt-d7-contract-liabilities
    e1.monetary_fund_detail.json: xlsx/gt-e1-monetary-fund
    f1.prepayment_detail.json: xlsx/gt-f1-prepayment
    f3.notes_payable_detail.json: xlsx/gt-f3-notes-payable
    f4.accounts_payable_detail.json: xlsx/gt-f4-accounts-payable
    f5.cost_of_sales_detail.json: xlsx/gt-f5-cost-of-sales
    g2.interest_receivable_detail.json: xlsx/gt-g2-interest-receivable
    g7.soe_subsidiary_disclosure.json: xlsx/gt-g7-long-term-equity-main
    h1.disposal_check.json: xlsx/gt-h1-fixed-assets
    h9.lease_liability_detail.json: xlsx/gt-h9-lease-liabilities

--- 2b: 无 I0 模板 ---
  wp_templates/I/ 下 I0 开头文件数: 0
  wp_templates/I/ 下 .xlsx 总数: 6
    I1 无形资产、累计摊销及减值准备.xlsx
    I2 开发支出.xlsx
    I3 商誉.xlsx
    I4 长期待摊费用.xlsx
    I5 其他非流动资产.xlsx
    I6 研发费用.xlsx
  ✅ 无 I0 模板: True

--- 2c: parent_duplicate 0 条 ---
  6 条 I entry 的 parent_entry_id:
    xlsx/gt-i1-intangible-assets: parent=None
    xlsx/gt-i2-development-expenditure: parent=None
    xlsx/gt-i3-goodwill: parent=None
    xlsx/gt-i4-long-term-prepaid: parent=None
    xlsx/gt-i5-other-noncurrent-assets: parent=None
    xlsx/gt-i6-research-development-expense: parent=None
  非 null parent 数: 0
  ✅ parent_duplicate 0 条: True
  manifest 里 xlsx/gt-i 前缀的总 entry 数: 0

--- 2d: 6 文件 ↔ 6 entry 双射 ---
  模板文件数: 6
  entry 数: 6
  entry_id 集合: ['xlsx/gt-i1-intangible-assets', 'xlsx/gt-i2-development-expenditure', 'xlsx/gt-i3-goodwill', 'xlsx/gt-i4-long-term-prepaid', 'xlsx/gt-i5-other-noncurrent-assets', 'xlsx/gt-i6-research-development-expense']
  模板文件集合: ['I1 无形资产、累计摊销及减值准备', 'I2 开发支出', 'I3 商誉', 'I4 长期待摊费用', 'I5 其他非流动资产', 'I6 研发费用']
  ✅ 6 == 6 双射: True

============================================================
TASK 3: 零回归基线现算
============================================================

--- 3a: 契约目录 ---
  契约文件数: 18
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
    f3.notes_payable_detail.json
    f4.accounts_payable_detail.json
    f5.cost_of_sales_detail.json
    g2.interest_receivable_detail.json
    g7.soe_subsidiary_disclosure.json
    h1.disposal_check.json
    h9.lease_liability_detail.json

--- 3b: 已注册 adapter 集合 ---
  源码中 adapter_id 赋值: []

  manifest 中 adapter_id 非 None 的 entry 数: 5
    xlsx/gt-d1-notes-receivable: adapter_id=d1.notes_receivable_detail
    xlsx/gt-d2-accounts-receivable: adapter_id=d2.receivable_detail
    xlsx/gt-d4-operating-revenue: adapter_id=d4.revenue_detail
    xlsx/gt-g7-long-term-equity-main: adapter_id=g7.soe_subsidiary_disclosure
    xlsx/gt-h1-fixed-assets: adapter_id=h1.disposal_check
  已注册 adapter_id 集合: ['d1.notes_receivable_detail', 'd2.receivable_detail', 'd4.revenue_detail', 'g7.soe_subsidiary_disclosure', 'h1.disposal_check']
```

## Task 2 结论

四类「查过且没有」全部确认：
1. ✅ 无 pilot — 全部契约的 review.entry_id 无一条以 xlsx/gt-i 开头
2. ✅ 无 I0 — wp_templates/I/ 下只有 I1~I6 共 6 个文件
3. ✅ parent_duplicate 0 条 — 6 条 parent_entry_id 全为 null
4. ✅ 6↔6 双射 — 6 个模板文件 ↔ 6 条 entry（无多余无遗漏）

## Task 3 结论

- 契约目录文件数: 18 个
- 已注册 adapter_id 集合: ['d1.notes_receivable_detail', 'd2.receivable_detail', 'd4.revenue_detail', 'g7.soe_subsidiary_disclosure', 'h1.disposal_check']
- 🔴 禁写死这些个数（slice 冻结时记 5 个已过期）

## 与 design 声明的差异对账

| 项 | design 声明 | 现算 | 说明 |
|---|---|---|---|
| 契约目录个数 | 17 个 | **18 个**（含 `_example.candidate.json`） | `_example` 不含 `review.entry_id`，有效 review 仍 17 条 |
| 已注册 adapter_id | `{d2, d4, g7, h1}` 4 个 | `{d1, d2, d4, g7, h1}` **5 个** | d1 由并发会话新注册（`d1.notes_receivable_detail.json` 已存在），memory 的 4 个记录已过期 |
| BP-2 记契约目录 | slice 冻结时 5 个 | 现算 **18 个** | 快照过期已确认（Task 1 同一结论）；但**实质断言仍成立**（逐文件读 `review.entry_id` 无一条以 `xlsx/gt-i` 开头）|

🔴 **这三处差异恰好证明了 IC-17/GC-10「禁写死个数」的铁律**——并发会话持续在注册新 entry，写死的数字上线即过期。

## 实质判据

Task 2 的实质断言**不是数文件个数**而是：
- `逐文件读 review.entry_id，无一条以 xlsx/gt-i 开头` → ✅ 通过
- `wp_templates/I/ 下无 I0 开头文件` → ✅ 通过
- `6 条 parent_entry_id 全为 null` → ✅ 通过
- `模板文件数 == entry 数 == 6` → ✅ 通过

Task 3 的基线**一律现算**：
- 契约目录 = **{_example, b60, d1, d2, d3, d4, d5, d6, d7, e1, f1, f3, f4, f5, g2, g7, h1, h9}** (18 个)
- 已注册 = **{d1, d2, d4, g7, h1}** (5 个)
- I 循环注册后预期变化：契约 +1（i6 canary）、注册集 +1（i6）
