# Task 0 — 前置依赖核查

**日期**：2026-09-27　**分支**：`work/2026-09-14-d4-dual-mode-p0-fixes`　**方法**：`git show HEAD:` 读 HEAD 版本

## 四项产物核查

| 产物 | 验证命令 | 结果 |
|---|---|---|
| `phase5_row_table_sheet.RowTableSheetSpec` | `git show HEAD:…/phase5_row_table_sheet.py \| grep "class RowTableSheetSpec"` | ✅ 命中 1 处：`class RowTableSheetSpec:` |
| `merge._protection` 格级判定 | `git show HEAD:…/merge.py \| grep "_protection"` | ✅ 命中 2 处：`def _protection(template: _FieldTemplate) -> ProtectionPolicy:` + 调用点 `protection_policy=self._protection(template),` |
| `StoreMergePlan.oo_crash_neutralization_fn` | `git show HEAD:…/store_item_registry.py \| grep "oo_crash_neutralization_fn"` | ✅ 字段声明 `oo_crash_neutralization_fn: str \| None = None`；HEAD 上已有 **2 个**消费者赋值（g7 + h1 各一处 `oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas"`），另有 g2 计划注释。共 6 处命中 |
| 🔴 `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas` **函数体** | `git show HEAD:…/g7_oo_crash_if_neutralize.py \| grep "^def \|_BARE_IF_CALL\|def _strip\|def _repack"` | ✅ **函数体在 HEAD**（不只是 import）：命中 7 处——`def neutralize_oo_crash_if_formulas(path: Path) -> tuple[str, ...]` + `_BARE_IF_CALL` 正则 `(?<![A-Za-z0-9_.])IF\s*\(` + `def _strip_bare_if_cells(xml: str)` + `def _repack_dropping(` |

## 🔴 关于「调用点在 HEAD、函数体从未落地」的历史

IC-9 特别要求确认**函数体**，因为历史上 `adapters/excel.py` 两处 import 跑在 `ImportError` 上。

本次核查结果：**函数体确实在 HEAD**（`git show HEAD:` 取到完整定义，含 `_BARE_IF_CALL` / `_strip_bare_if_cells` / `_repack_dropping` 三个内部函数/常量），IC-9 可实施。

同源结论：与 G 循环 Task 0（`g-cycle-sync-foundation-and-first-canary/evidence/task0-prerequisites.md`）和 H 循环 Task 0（`h-cycle-sync-foundation-and-first-canary/evidence/task0-prerequisites.md`）一致。

## 结论

四项前置产物**全部在 HEAD 可用**，Task 1 及后续可安全进行。
