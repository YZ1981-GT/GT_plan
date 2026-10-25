"""用户自定义公式跨模块引用：L1 handler + 参数提取函数单元测试。

spec: formula-push-user-custom-cross-module · Task 5/6
纯函数测试，不需要数据库。
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.formula_engine import (
    FormulaContext,
    FormulaResult,
    _extract_note_refs,
    _extract_wp_refs,
    execute,
)


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_wp_refs
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractWpRefs:
    def test_single_wp(self):
        refs = _extract_wp_refs("WP('D2','审定数')")
        assert refs == [("D2", "审定数")]

    def test_wp_cell_address(self):
        refs = _extract_wp_refs("WP('E1','B5')")
        assert refs == [("E1", "B5")]

    def test_wp_default_column(self):
        """单参 WP 应默认 '审定数'"""
        refs = _extract_wp_refs("WP('K1')")
        assert refs == [("K1", "审定数")]

    def test_multiple_wp(self):
        formula = "WP('D2','审定数') + WP('K1','B3')"
        refs = _extract_wp_refs(formula)
        assert len(refs) == 2
        assert ("D2", "审定数") in refs
        assert ("K1", "B3") in refs

    def test_no_wp(self):
        refs = _extract_wp_refs("TB('1001','期末余额')")
        assert refs == []

    def test_mixed_formula(self):
        formula = "WP('D2','审定数') + TB('1001','期末余额') - NOTE('五、1','合计')"
        refs = _extract_wp_refs(formula)
        assert refs == [("D2", "审定数")]


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_note_refs
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractNoteRefs:
    def test_single_note(self):
        refs = _extract_note_refs("NOTE('五、1','货币资金','end_amount')")
        assert refs == [("五、1", "货币资金")]

    def test_two_param_note(self):
        refs = _extract_note_refs("NOTE('五、1','合计')")
        assert refs == [("五、1", "合计")]

    def test_single_param_note(self):
        refs = _extract_note_refs("NOTE('五、1')")
        assert refs == [("五、1", "合计")]

    def test_multiple_notes(self):
        formula = "NOTE('五、1','合计') + NOTE('五、2','期末余额')"
        refs = _extract_note_refs(formula)
        assert len(refs) == 2

    def test_no_note(self):
        refs = _extract_note_refs("TB('1001','期末余额')")
        assert refs == []


# ═══════════════════════════════════════════════════════════════════════════════
# L1 handler 求值（FormulaContext 含预载数据时返回正确值）
# ═══════════════════════════════════════════════════════════════════════════════


class TestWpHandlerExecution:
    """WP() L1 handler 在 wp_data 有值时返回正确结果。"""

    def test_wp_returns_value(self):
        ctx = FormulaContext(
            wp_data={"D2": {"审定数": Decimal("12345.67")}},
        )
        result = execute("WP('D2','审定数')", ctx)
        assert result.value == Decimal("12345.67")
        assert not result.errors

    def test_wp_missing_code_returns_zero(self):
        ctx = FormulaContext(wp_data={})
        result = execute("WP('D2','审定数')", ctx)
        assert result.value == Decimal("0")
        assert not result.errors

    def test_wp_missing_column_returns_zero(self):
        ctx = FormulaContext(
            wp_data={"D2": {"期末余额": Decimal("100")}},
        )
        result = execute("WP('D2','审定数')", ctx)
        assert result.value == Decimal("0")

    def test_wp_cell_address(self):
        ctx = FormulaContext(
            wp_data={"E1": {"B5": Decimal("999")}},
        )
        result = execute("WP('E1','B5')", ctx)
        assert result.value == Decimal("999")

    def test_wp_arithmetic(self):
        ctx = FormulaContext(
            wp_data={
                "D2": {"审定数": Decimal("100")},
                "K1": {"B3": Decimal("50")},
            },
        )
        result = execute("WP('D2','审定数') + WP('K1','B3')", ctx)
        assert result.value == Decimal("150")


class TestNoteHandlerExecution:
    """NOTE() L1 handler 在 note_data 有值时返回正确结果。"""

    def test_note_returns_value(self):
        ctx = FormulaContext(
            note_data={"五、1": {"合计": Decimal("88888")}},
        )
        result = execute("NOTE('五、1','合计')", ctx)
        assert result.value == Decimal("88888")
        assert not result.errors

    def test_note_missing_section_returns_zero(self):
        ctx = FormulaContext(note_data={})
        result = execute("NOTE('五、1','合计')", ctx)
        assert result.value == Decimal("0")

    def test_note_arithmetic_with_tb(self):
        ctx = FormulaContext(
            tb_data={"1001": {"期末余额": Decimal("1000")}},
            note_data={"五、1": {"合计": Decimal("1000")}},
        )
        result = execute("TB('1001','期末余额') - NOTE('五、1','合计')", ctx)
        assert result.value == Decimal("0")


class TestCrossModuleMixed:
    """跨模块混合公式：TB + WP + NOTE 联合求值。"""

    def test_three_way_formula(self):
        ctx = FormulaContext(
            tb_data={"1001": {"期末余额": Decimal("500")}},
            wp_data={"D2": {"审定数": Decimal("200")}},
            note_data={"五、1": {"合计": Decimal("300")}},
        )
        result = execute("TB('1001','期末余额') + WP('D2','审定数') - NOTE('五、1','合计')", ctx)
        # 500 + 200 - 300 = 400
        assert result.value == Decimal("400")
        assert not result.errors

    def test_nested_math(self):
        ctx = FormulaContext(
            wp_data={"D2": {"审定数": Decimal("-50")}},
        )
        result = execute("ABS(WP('D2','审定数'))", ctx)
        assert result.value == Decimal("50")


# ═══════════════════════════════════════════════════════════════════════════════
# wp_formula_linkage_service.expression_references_cell — 缺陷 2 修复验证
# ═══════════════════════════════════════════════════════════════════════════════

from app.services.wp_formula_linkage_service import (
    expression_references_cell,
    extract_wp_refs,
)


class TestExpressionReferencesCell:
    """验证 expression_references_cell 在各场景下的匹配行为。"""

    def test_exact_cell_match(self):
        assert expression_references_cell("WP('D2','审定数')", "D2", "审定数")

    def test_exact_cell_no_match(self):
        assert not expression_references_cell("WP('D2','审定数')", "D2", "B5")

    def test_wrong_wp_code(self):
        assert not expression_references_cell("WP('D2','审定数')", "K1", "审定数")

    def test_empty_cell_matches_any_ref(self):
        """🔴 缺陷 2 修复：空 cell_or_col = 底稿级传播，只要引用了该 wp_code 就命中。"""
        assert expression_references_cell("WP('D2','审定数')", "D2", "")

    def test_empty_cell_no_match_wrong_code(self):
        assert not expression_references_cell("WP('D2','审定数')", "K1", "")

    def test_none_cell_matches_any_ref(self):
        """None 等同于空字符串。"""
        # expression_references_cell 签名是 str，但调用方可能传 None 经 str() 后为 ""
        assert expression_references_cell("WP('D2','审定数')", "D2", "")

    def test_multiple_refs_empty_cell(self):
        expr = "WP('D2','审定数') + WP('K1','B3')"
        assert expression_references_cell(expr, "D2", "")
        assert expression_references_cell(expr, "K1", "")
        assert not expression_references_cell(expr, "E1", "")

    def test_case_insensitive_cell(self):
        """cell 匹配应 upper 后比对。"""
        assert expression_references_cell("WP('D2','B5')", "D2", "b5")

    def test_no_wp_refs(self):
        assert not expression_references_cell("TB('1001','期末余额')", "D2", "")


class TestExtractWpRefsLinkage:
    """验证 linkage service 的 extract_wp_refs（与 formula_engine 的同名函数独立实现）。"""

    def test_two_param(self):
        refs = extract_wp_refs("WP('D2','审定数')")
        assert refs == [("D2", "审定数")]

    def test_three_param_d23(self):
        refs = extract_wp_refs("WP('D2','坏账准备明细表D2-3','本期计提合计')")
        assert refs == [("D2", "坏账准备明细表D2-3.本期计提合计")]

    def test_empty(self):
        assert extract_wp_refs("") == []
        assert extract_wp_refs("TB('1001','期末余额')") == []
