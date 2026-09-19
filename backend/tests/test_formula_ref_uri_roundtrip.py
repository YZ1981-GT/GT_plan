"""Unit tests for formula_ref ↔ URI round-trip (R10.3).

Verifies that the fix to formula_ref_to_uri() preserves the third argument
(semantic name not discarded), and tests the ACNR grammar.py bidirectional
conversion functions.

Requirements: 10.3
"""

import pytest

from app.services.address_registry import formula_ref_to_uri, uri_to_formula_ref
from app.services.acnr.grammar import (
    formula_ref_to_uri as acnr_formula_ref_to_uri,
    uri_to_formula_ref as acnr_uri_to_formula_ref,
)


class TestFormulaRefToUri3ArgWP:
    """WP() 3 参 → URI 保留第三参（修复核心缺陷）。"""

    def test_wp_3arg_cell(self):
        """WP('D2','明细表D2-2','E100') → wp://D2/明细表D2-2#E100"""
        uri = formula_ref_to_uri("WP('D2','明细表D2-2','E100')")
        assert uri == "wp://D2/明细表D2-2#E100"

    def test_wp_3arg_semantic(self):
        """WP('D2','明细表D2-2','合计行-期末余额') → wp://D2/明细表D2-2#合计行-期末余额"""
        uri = formula_ref_to_uri("WP('D2','明细表D2-2','合计行-期末余额')")
        assert uri == "wp://D2/明细表D2-2#合计行-期末余额"

    def test_wp_3arg_chinese_sheet(self):
        """WP('F3','核销明细表F3-3','审定数') → wp://F3/核销明细表F3-3#审定数"""
        uri = formula_ref_to_uri("WP('F3','核销明细表F3-3','审定数')")
        assert uri == "wp://F3/核销明细表F3-3#审定数"


class TestFormulaRefToUri2ArgWP:
    """WP() 2 参 → URI 不变。"""

    def test_wp_2arg_custom_flat(self):
        """WP('CUST-01','B7') → wp://CUST-01/B7"""
        uri = formula_ref_to_uri("WP('CUST-01','B7')")
        assert uri == "wp://CUST-01/B7"

    def test_wp_2arg_standard_sheet(self):
        """WP('D2','明细表D2-2') → wp://D2/明细表D2-2"""
        uri = formula_ref_to_uri("WP('D2','明细表D2-2')")
        assert uri == "wp://D2/明细表D2-2"


class TestFormulaRefToUriPREV:
    """PREV 双语义：2 参→tb, 3 参→wp。"""

    def test_prev_2arg_tb(self):
        """PREV('1002','期末余额') → tb://1002#期末余额"""
        uri = formula_ref_to_uri("PREV('1002','期末余额')")
        assert uri == "tb://1002#期末余额"

    def test_prev_3arg_wp(self):
        """PREV('D2','审定表D2-1','审定数') → wp://D2/审定表D2-1#审定数"""
        uri = formula_ref_to_uri("PREV('D2','审定表D2-1','审定数')")
        assert uri == "wp://D2/审定表D2-1#审定数"


class TestUriToFormulaRef3ArgWP:
    """URI → WP() 3 参还原。"""

    def test_uri_to_3arg(self):
        """wp://D2/明细表D2-2#E100 → WP('D2','明细表D2-2','E100')"""
        ref = uri_to_formula_ref("wp://D2/明细表D2-2#E100")
        assert ref == "WP('D2','明细表D2-2','E100')"

    def test_uri_to_3arg_semantic(self):
        """wp://D2/明细表D2-2#合计行-期末余额 → WP('D2','明细表D2-2','合计行-期末余额')"""
        ref = uri_to_formula_ref("wp://D2/明细表D2-2#合计行-期末余额")
        assert ref == "WP('D2','明细表D2-2','合计行-期末余额')"

    def test_uri_to_2arg(self):
        """wp://CUST-01/B7 → WP('CUST-01','B7')"""
        ref = uri_to_formula_ref("wp://CUST-01/B7")
        assert ref == "WP('CUST-01','B7')"

    def test_uri_to_2arg_sheet_level(self):
        """wp://D2/明细表D2-2 → WP('D2','明细表D2-2')"""
        ref = uri_to_formula_ref("wp://D2/明细表D2-2")
        assert ref == "WP('D2','明细表D2-2')"


class TestRoundTrip:
    """无损往返：formula_ref → URI → formula_ref 等价（R10.3 铁律）。"""

    @pytest.mark.parametrize("formula_ref", [
        "WP('D2','明细表D2-2','E100')",
        "WP('D2','明细表D2-2','合计行-期末余额')",
        "WP('CUST-01','B7')",
        "WP('D2','明细表D2-2')",
        "WP('F3','核销明细表F3-3','审定数')",
        "WP('H1','审定表H1-1','期末余额')",
    ])
    def test_wp_roundtrip(self, formula_ref: str):
        """WP formula_ref → URI → formula_ref 无损。"""
        uri = formula_ref_to_uri(formula_ref)
        assert uri is not None, f"formula_ref_to_uri({formula_ref!r}) 返回 None"
        restored = uri_to_formula_ref(uri)
        assert restored == formula_ref, (
            f"往返不一致: {formula_ref!r} → {uri!r} → {restored!r}"
        )

    @pytest.mark.parametrize("formula_ref", [
        # NOTE and AUX have path segments and roundtrip correctly
        "NOTE('五、3','合计','期末')",
        "AUX('1122','甲公司','期末')",
    ])
    def test_non_wp_roundtrip(self, formula_ref: str):
        """非 WP 域 formula_ref → URI → formula_ref 无损。"""
        uri = formula_ref_to_uri(formula_ref)
        assert uri is not None
        restored = uri_to_formula_ref(uri)
        assert restored == formula_ref


class TestAcnrGrammarInterop:
    """ACNR grammar.py 层互转函数（委托 parse_wp_formula）。"""

    @pytest.mark.parametrize("formula_ref,expected_uri", [
        ("WP('D2','明细表D2-2','E100')", "wp://D2/明细表D2-2#E100"),
        ("WP('D2','明细表D2-2','合计行-期末余额')", "wp://D2/明细表D2-2#合计行-期末余额"),
        ("WP('CUST-01','B7')", "wp://CUST-01/B7"),
        ("WP('D2','明细表D2-2')", "wp://D2/明细表D2-2"),
        ("PREV('D2','审定表D2-1','审定数')", "wp://D2/审定表D2-1#审定数"),
        ("PREV('1002','期末余额')", "tb://1002#期末余额"),
    ])
    def test_acnr_formula_ref_to_uri(self, formula_ref: str, expected_uri: str):
        """ACNR grammar.formula_ref_to_uri 与 address_registry 一致。"""
        uri = acnr_formula_ref_to_uri(formula_ref)
        assert uri == expected_uri

    @pytest.mark.parametrize("uri,expected_ref", [
        ("wp://D2/明细表D2-2#E100", "WP('D2','明细表D2-2','E100')"),
        ("wp://D2/明细表D2-2#合计行-期末余额", "WP('D2','明细表D2-2','合计行-期末余额')"),
        ("wp://CUST-01/B7", "WP('CUST-01','B7')"),
        ("wp://D2/明细表D2-2", "WP('D2','明细表D2-2')"),
    ])
    def test_acnr_uri_to_formula_ref(self, uri: str, expected_ref: str):
        """ACNR grammar.uri_to_formula_ref WP 域解析正确。"""
        ref = acnr_uri_to_formula_ref(uri)
        assert ref == expected_ref

    @pytest.mark.parametrize("formula_ref", [
        "WP('D2','明细表D2-2','E100')",
        "WP('D2','明细表D2-2','合计行-期末余额')",
        "WP('CUST-01','B7')",
        "WP('D2','明细表D2-2')",
    ])
    def test_acnr_roundtrip(self, formula_ref: str):
        """ACNR grammar 层无损往返。"""
        uri = acnr_formula_ref_to_uri(formula_ref)
        assert uri is not None
        restored = acnr_uri_to_formula_ref(uri)
        assert restored == formula_ref

    def test_acnr_non_wp_delegates(self):
        """非 WP/PREV 域委托 address_registry。"""
        uri = acnr_formula_ref_to_uri("TB('1001','审定数')")
        assert uri == "tb://1001#审定数"
        # NOTE 域 round-trip
        uri2 = acnr_formula_ref_to_uri("NOTE('五、3','合计','期末')")
        assert uri2 == "note://五、3/合计#期末"
        ref2 = acnr_uri_to_formula_ref("note://五、3/合计#期末")
        assert ref2 == "NOTE('五、3','合计','期末')"
