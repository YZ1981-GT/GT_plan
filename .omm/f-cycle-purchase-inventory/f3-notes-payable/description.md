# F3 应付票据（2201）

componentType `f3-notes-payable`，主入口 `GtF3NotesPayable.vue`，后端 `_f3_notes_payable.py`。

## Tab 组成（`f3/`）

| 组件 | 作用 |
|---|---|
| `F3TabAdjudication` | 审定表（未审/AJE/RJE/审定），TB 2201 核对 |
| `F3TabDetail` | 票据明细（票据种类/出票日/到期日/金额/收款人/是否带息/保证金） |
| `F3TabAdjustment` | 调整分录（AJE/RJE，回写审定表） |
| `F3TabInterestCalc` | 带息票据利息测算 |
| `F3TabOverdueCheck` | 逾期票据检查（`unpaidAmount` / `riskFlags`） |
| `F3TabRelatedParty` | 关联方票据 |
| `F3TabVoucherCheck` + `F3VoucherCheckTable` / `F3VoucherCheckDialog` | 凭证级检查（引导弹窗 + 矩阵表） |
| `F3TabDisclosureListed` / `F3TabDisclosureSOE` | 附注披露（**五、36 / 八、36**，权威 `note_template_variant_matrix.ying_fu_piao_ju`） |
| `F3ImportExportToolbar` / `F3SheetAttachments` | 统一导入导出 ▾ / 附件 |

## 关键机制

- **TB 种子**：`useF3FormData.seedTrialBalance()` 把 `tbValues['2201']` 种到 `F3-1-adj-tb-2201`，
  **仅无持久化时 seed，不覆盖手工录入**
- **票据类别动态聚合**：审定表与附注按 `noteType` 动态聚合（银行承兑 / 商业承兑 / **供应链票据**），
  早期硬编码两类导致供应链票据丢失且合计口径不一致，已修
- **附注同步**：`f3NoteSectionMap.ts` 的 `buildF3SyncPayload` 推 `sub_table_data`（种类 × 期末余额/上年年末余额）+
  `_sub_table_columns` 列头，已登记进披露列头覆盖率守卫
- **正反向跳转**：附注 五、36/八、36 ↔ F3 披露 sheet（`noteDisclosureJump` / `ReverseJump`）

## 与其他循环的关系

- 票据结算：F4 应付账款（以票抵账）、E1 货币资金（保证金受限）
- 贴现/敞口：L1 短期借款（逾期银行承兑重分类 2001）
- 带息票据利息：L2 应付利息（当前未勾稽，见 todo）
- 附注 CAS23 / 央行 2022 第 4 号（供应链票据）
