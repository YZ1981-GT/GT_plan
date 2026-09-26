# Task 2 证据：形态判定 + 几何逐格实测 + 下游消费方 grep 补全

**日期**：2026-09-26

## 1. 七个受管区几何复核（design §受管区清单逐项核对）

| sheet_key | managed_sheet | store_item_id | 表头 | 数据 | footer | UUID | formula_columns | binding_kind | row_identity |
|---|---|---|---|---|---|---|---|---|---|
| `f16-managed` | 关联方及交易检查表F1-6 | `F1-rp-rows` | R6 | R7-9 | R10 | N | F, H | excel_table | rowId |
| `f15-managed` | 长期挂款检查表F1-5 | `F1-lt-rows` | R5 | R6-14 | R15 | N | () 空 | excel_table | rowId |
| `f17-current` | 预付账款检查表F1-7 | `F1-vc-current-rows` | R15/R16 | R17-37 | R38 | T | () 空 | excel_table | rowId |
| `f17-credit` | 同上 | `F1-vc-credit-rows` | R40/R41 | R42-64 | R65 | T | () 空 | excel_table | rowId |
| `f17-post` | 同上 | `F1-vc-post-rows` | R67/R68 | R69-85 | R86 | T | () 空 | excel_table | rowId |
| `f14-suppliers` | 实质性分析F1-4 | `F1-ana-pack`(suppliers[]) | R40 | R41-50 | R51 | S | E, G | dict 子数组 | rowId |
| `f12-managed` | 明细表F1-2 | `F1-det-rows` | R12/R13 | R14-34 | R35 | AF | H, O, Q, X | excel_table | rowId |

UUID 列逐项确认（spec requirements.md §模板实测已列，grep 前端 composable 交叉核对）。

## 2. 三元组实证表（按值 grep + composable 源码逐字核对）

| sheet | store 键 | addRow/removeRow | composable | binding_kind |
|---|---|---|---|---|
| F1-6 | `F1-rp-rows` (useF1RelatedParty:85) | addRow×1/removeRow×1 | useF1RelatedParty | excel_table |
| F1-5 | `F1-lt-rows` (useF1LongTerm:42) | addRow×1/removeRow×1 | useF1LongTerm | excel_table |
| F1-7 区① | `F1-vc-current-rows` (useF1ComprehensiveCheck:359) | addSample('current')×1/removeSample×1 | useF1ComprehensiveCheck | excel_table |
| F1-7 区② | `F1-vc-credit-rows` (useF1ComprehensiveCheck:361) | addSample('credit')×1/removeSample×1 | 同上 | excel_table |
| F1-7 区③ | `F1-vc-post-rows` (useF1ComprehensiveCheck:362) | addSample('post')×1/removeSample×1 | 同上 | excel_table |
| F1-4 区④ | `F1-ana-pack.suppliers[]` (useF1Analysis:82) | addSupplierRow×1/removeSupplierRow×1 | useF1Analysis | dict 子数组 |
| F1-2 | `F1-det-rows` (useF1Detail:78) | addRow×1/removeRow×1 | useF1Detail | excel_table |

🔴 键名陷阱确认：
- F1-7 区①键名是 `F1-vc-current-rows`（注释说"兼容原 F1-7 导入 item_id"），**不是** `F1-vc-debit-rows`
- `F1-rp-rows` 是正确值，**不是** `F1-6-rows`

## 3. 下游消费方 grep 补全

| store_item_id | 生产引用数 | 消费方清单 |
|---|---|---|
| `F1-det-rows` | 18 | useF1Detail(L78) / useF1CrossSheet(L152) / useF1Analysis(L613) / useF1ConfirmationProcedure(L6) / useF1DisclosureListed(L302) / useF1DisclosureSoe(L450) / useF1DetailAutoSeed(L22,L69) / GtF1Prepayment(L392) / F1TabComprehensiveCheck(L846,L874,L944) / _f1_import_export(L283) / e2e(L15,L183) + 4 测试文件 |
| `F1-aje-rows` | 7 | useF1Adjustment(L49) / useF1CrossSheet(L304) / useF1LongTerm(L328,L334,L346) / F1TabAdjustment(L225) / e2e(L17) |
| `F1-lt-rows` | 5 | useF1LongTerm(L42) / useF1DisclosureSoe(L100) / _f1_import_export(L284) / e2e(L16) + f1SoeOver1Source.spec |
| `F1-rp-rows` | 2 | useF1RelatedParty(L85) / _f1_import_export(L285) |
| `F1-ana-pack` | 1 | useF1Analysis(L82) |
| `F1-vc-current-rows` | 2 | useF1ComprehensiveCheck(L359) / _f1_import_export(L286) |
| `F1-vc-credit-rows` | 2 | useF1ComprehensiveCheck(L360) / _f1_import_export(L287) |
| `F1-vc-post-rows` | 3 | useF1ComprehensiveCheck(L361) / useF1CrossSheet(L354) / _f1_import_export(L288) |

## 4. 红基线 B3（缺 rowId 旧行载入）

F1 五个 `-rows` 键载入路径全部 `raw.rowId || generateRowId()`（无下标回退）。
缺 `rowId` 的旧行每次载入现铸新 id（id 不稳定），但：
- 只在首次载入时发生（前端立即回写 → 之后 id 稳定）
- 真库 68 行全带 `rowId`（实测 spec requirements.md），当前无缺 id 行
- **F1 无 BP-7**（slice `capability_target_blocked_by` 不含 BP-7）

结论：F1 不需要下标回退迁移。
