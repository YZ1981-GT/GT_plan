# -*- coding: utf-8 -*-
"""D4-9 用户自定义公式管理 —— 行为级验证（judge-first）。

spec: d4-9-customer-structure-bidirectional-writeback · Task 9
Requirements 5.1/5.2/5.3/5.4/5.5/5.6 · Property 6/7

判据：
1. 运行时保护集合 = 契约静态 formula_mask ∪ 用户公式 cell（Requirement 5.3/5.6）。
2. 用户公式 cell 落别的 sheet / 非受管区 / 非法 A1 → 不进保护集合（fail-safe 过滤）。
3. user_formulas_for_xlsx 产出 {sheet!cell: {formula}} 供 _fill_workpaper_data 覆盖
   （用户公式优先，Requirement 5.1）。
4. 血缘：占比 D/F→C/E+总额、合计→明细区间、总额←D4-7 取数登记（Requirement 5.4/5.5）；
   总额取数 manual_override_preserved=True（不覆盖手工值）。
5. 变异守卫：把用户公式 cell 排除出保护集合（模拟 Task 11 变异）→ 该 cell 不在保护集合
   ⇒ OO 覆盖不会产生受保护冲突（RED 信号）。
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.workpaper_sync import phase5_d4_customer_structure as m


def _wf(sheet, cell, expr="=1", source="custom"):
    return SimpleNamespace(
        sheet_name=sheet, target_cell=cell, expression=expr, formula_source=source
    )


SHEET = m.MANAGED_SHEET_D49


# ═══ 判据 1：保护集合 = 静态 mask ∪ 用户公式 cell ═══
def test_runtime_protected_is_union_of_static_mask_and_user_cells() -> None:
    formulas = [_wf(SHEET, "$C$24", "=D4-7!D26", "reference"), _wf(SHEET, "C16", "=C15*2")]
    protected = set(m.runtime_protected_cells(formulas))
    # 用户公式 cell 进保护集合
    assert "C24" in protected
    assert "C16" in protected
    # 契约静态 formula_mask cell（D/F 占比、合计）也在
    assert "D13" in protected
    assert "F27" in protected
    assert "C23" in protected  # 本期合计
    # 无用户公式时 = 纯静态 mask
    static_only = set(m.runtime_protected_cells([]))
    assert static_only == set(m.runtime_protected_cells([])) and "D13" in static_only
    assert protected == static_only | {"C24", "C16"}


def test_runtime_user_formula_cells_extracts_only_d49_managed() -> None:
    formulas = [
        _wf(SHEET, "C24"),           # 受管区 ✓
        _wf(SHEET, "B18"),           # 受管数据行 ✓
        _wf("别的表D4-8", "A1"),      # 别的 sheet ✗
        _wf(SHEET, "A99"),           # 非受管区（行 99）✗
        _wf(SHEET, "not_a_cell"),    # 非法 A1 ✗
    ]
    cells = m.runtime_user_formula_cells(formulas)
    assert cells == ("B18", "C24"), f"只认 D4-9 受管区可解析 cell，实得 {cells}"


# ═══ 判据 3：xlsx 覆盖 dict ═══
def test_user_formulas_for_xlsx_maps_sheet_cell_to_formula() -> None:
    formulas = [_wf(SHEET, "C24", "=D4-7!D26", "reference"), _wf(SHEET, "C16", "C15*2")]
    out = m.user_formulas_for_xlsx(formulas)
    assert out[f"{SHEET}!C24"]["formula"] == "=D4-7!D26"
    # 无 = 前缀的自动补齐
    assert out[f"{SHEET}!C16"]["formula"] == "=C15*2"
    assert out[f"{SHEET}!C24"]["source"] == "reference"


# ═══ 判据 4：血缘 ═══
def test_formula_lineage_declares_ratio_sum_and_autosource() -> None:
    lineage = m.formula_lineage()
    # 占比 D→C+总额
    assert "$C$24" in lineage["D13:D22"]["refs"]
    assert "C13:C22" in lineage["D13:D22"]["refs"]
    # 合计→明细区间
    assert lineage["C23"]["refs"] == ["C13:C22"]
    # 总额←D4-7 取数 + 手工覆盖保留
    assert "D4-7!D26" in lineage["C24"]["refs"]
    assert lineage["C24"]["manual_override_preserved"] is True


# ═══ 判据 5：变异守卫 —— 排除用户公式 cell 后它不在保护集合（RED 信号）═══
def test_mutation_excluding_user_cell_drops_it_from_protection() -> None:
    """模拟 Task 11 变异：故意让用户公式 cell 不进保护集合。

    若 runtime_user_formula_cells 被改成空返回，用户公式 cell 就不在 protected 集合，
    OO 侧覆盖不会产生受保护冲突（AC 5.6 失守）。本判据钉住「用户公式 cell 必须并入」。
    """
    formulas = [_wf(SHEET, "C24", "=D4-7!D26")]
    # 正常：C24 在保护集合
    assert "C24" in set(m.runtime_protected_cells(formulas))
    # 缺陷版（只取静态 mask，忽略用户公式）→ C24 不在
    static_only = set(m.runtime_protected_cells([]))
    assert "C24" not in static_only, (
        "静态 formula_mask 不含可编辑 cell C24 —— 证明必须靠用户公式并入才受保护"
    )
