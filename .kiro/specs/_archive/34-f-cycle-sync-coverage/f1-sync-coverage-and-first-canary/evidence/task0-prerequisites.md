# Task 0 前置依赖核查证据

**日期**：2026-09-26　**判定方式**：`git show HEAD:` + grep 实证

## 前置 A：RowTableSheetSpec / StoreKind / AgingLayout

✅ 三者均在 `backend/app/services/workpaper_sync/phase5_row_table_sheet.py`：

- `StoreKind`（Enum）：4 成员 `rows/dict/fixed_text/dedicated`
- `AgingLayout`（Enum）：2 成员 `nested/flat`
- `AgingGroupSpec`（frozen dataclass）：`json_prefix / group_header_cell / segments / leaf_labels`
- `RowTableSheetSpec`（frozen dataclass）：含 `managed_sheet / sheet_key / table_key / template_id / table_name / uuid_col / first_data_row / last_data_row / footer_row / binding_kind / store_item_id / store_kind / row_identity_key / field_specs / formula_columns / formula_templates / aging_layout / aging_groups / footer_marker / footer_carries_total_formula / error_label / html_only_item_ids / ghost_row_anchor_index`
- `formula_mask` property 由 `formula_columns × [first_data_row, last_data_row]` 现算

## 前置 B：AdjudicationSheetSpec 含 fixed_rows / slot_driven

✅ 在 `backend/app/services/workpaper_sync/phase5_adjudication_sheet.py`：

- `AdjudicationRowMode`（Enum）：含 `slot_driven` 成员
- `AdjudicationSheetSpec`（frozen dataclass）：`row_mode: AdjudicationRowMode` + `sections: tuple[AdjudicationSection, ...]` + `cell_mask` + `is_cell_masked(column, row)` 格级判定
- 🔴 spec 原文写 `fixed_rows` 作为 row_mode 名称，实际枚举成员名待 Task 20 实施时逐字核对（不影响前置判定）

## 前置 C：merge._protection 格级判定

✅ `backend/app/services/workpaper_sync/merge.py`：

- `PROTECTED_MODES` 从 `contracts` 导入（L115）
- `_protection(template)` 静态方法（L773）：三类只读来源分别登记
- `protection_policy=self._protection(template)` 在字段构造时调用（L900）

## 结论

三个前置条件全部满足，后续 Task 可正常实施。
