# Task 5 证据：F2-P11 零回归基线

**现算日期**：2026-09-26
**契约目录**：`backend/data/workpaper_sync_contracts/`
**总数**：13 个（含 1 个 example.candidate）

## 现有 contract golden digest（SHA-256 of file bytes）

| contract_id | version | sha256 | file |
|---|---|---|---|
| example.candidate | 0.0.0-candidate | `4e85a633550b8f60…` | _example.candidate.json |
| b60.hour_budget | 1.0.0 | `91beaa2a284fd8d2…` | b60.hour_budget.json |
| d1.notes_receivable_detail | 1.0.0 | `62b589551bd99050…` | d1.notes_receivable_detail.json |
| d2.receivable_detail | 1.0.0 | `078b04377a34054f…` | d2.receivable_detail.json |
| d3.prepaid_receipts_detail | 1.0.0 | `4f5b71fd73c1c412…` | d3.prepaid_receipts_detail.json |
| d4.revenue_detail | 1.2.0 | `5bd890211ac8f897…` | d4.revenue_detail.json |
| d5.receivables_financing_detail | 1.0.0 | `03900069af256db6…` | d5.receivables_financing_detail.json |
| d6.contract_assets_detail | 1.0.0 | `a8ba5bf29129728c…` | d6.contract_assets_detail.json |
| d7.contract_liabilities_detail | 1.0.0 | `84b266b5e9efc45f…` | d7.contract_liabilities_detail.json |
| e1.monetary_fund_detail | 1.0.0 | `4a0cf6c928566c96…` | e1.monetary_fund_detail.json |
| f1.prepayment_detail | 1.0.0 | `9ea57f744d34533a…` | f1.prepayment_detail.json |
| g7.soe_subsidiary_disclosure | 1.0.0 | `3c992e2f31540f14…` | g7.soe_subsidiary_disclosure.json |
| h1.disposal_check | 1.0.0 | `e7d6c1b75af2d600…` | h1.disposal_check.json |

## 零回归规则

- F2 新增的四个契约文件（`f2.inventory_main.json` / `f2.stocktake_bundle.json` / `f2.inventory_valuation.json` / `f2.inventory_special.json`）不得改动上述 13 个文件的任何字节。
- 判据：对上述 13 个文件重新 `sha256(file_bytes)`，与本表逐字比对。
