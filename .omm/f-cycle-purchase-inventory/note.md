# 说明

产出方式、字段约定、维护约定见 `.omm/d-cycle-sales/note.md`。

## 本 perspective 的事实来源

- 8 个 componentType（`f1-prepayment` / `f2-inventory-main` / `f2-inventory-special` /
  `f2-inventory-valuation-impairment` / `f2-stocktake-bundle` / `f3-notes-payable` / `f4-accounts-payable` /
  `f5-cost-of-sales`）→ `htmlRendererRegistry.ts`
- 5 个后端 render 策略（`_f1_prepayment` / `_f2_inventory_main` / `_f2_inventory_valuation_impairment` /
  `_f2_inventory_special` / `_f2_stocktake` / `_f3_notes_payable` / `_f4_accounts_payable` / `_f5_cost_of_sales`）
  → `wp_render_strategies/__init__.py`
- 各科目 Tab 组件与子目录 → 逐个 `list_directory`（f1 / f2 含 7 子目录 / f2-special 含 contract+ipo /
  f3-notes-payable / f4-accounts-payable / f5-cost-of-sales）
- 科目码：F1=1123（`useF1FormData` writeback）、F3=2201（`useF3FormData.seedTrialBalance`）、
  F2 科目族 1401~1411 / 1412 进销差价 / 1471 跌价准备（`f2AccountModel.ts` 注释与常量）
- F4=2202、F5=6401 来自各自 composable 的科目常量（本轮以 `f2AccountModel` 中 6401 主营业务成本条目与既有实现为据）

## 未核实项

- F2 四个入口各自的 sheet ↔ Tab 精确映射（未逐一读四个主入口的 `v-if` 分发链；本文按目录分组描述，不声称是 sheet 编号映射）
- F5 的 TB 回写科目常量未直接读取（按 6401 营业成本记载）
