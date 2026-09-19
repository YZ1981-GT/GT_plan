"""Test parse_wp_formula() for WP()/PREV() 2-arg and 3-arg parsing.

Task 7.1: 在 formula_grammar.py 实现 WP()/PREV() 的 2 参与 3 参解析
Requirements: 10.2, 10.5
"""

import pytest

from app.services.formula_grammar import (
    FormulaParseError,
    FormulaProfile,
    ParsedFormula,
    parse_wp_formula,
)


class TestParseWpFormula3Arg:
    """3-arg (standard profile) WP/PREV parsing."""

    def test_wp_standard_cell(self):
        """WP('D2','明细表D2-2','E100') → standard profile."""
        r = parse_wp_formula("WP('D2','明细表D2-2','E100')")
        assert r.func_name == "WP"
        assert r.args == ["D2", "明细表D2-2", "E100"]
        assert r.arity == 3
        assert r.profile == "standard"

    def test_wp_standard_semantic(self):
        """WP('D2','明细表D2-2','合计行-期末余额') → standard profile."""
        r = parse_wp_formula("WP('D2','明细表D2-2','合计行-期末余额')")
        assert r.func_name == "WP"
        assert r.args == ["D2", "明细表D2-2", "合计行-期末余额"]
        assert r.arity == 3
        assert r.profile == "standard"

    def test_prev_standard(self):
        """PREV('D2','明细表D2-2','E100') → standard profile."""
        r = parse_wp_formula("PREV('D2','明细表D2-2','E100')")
        assert r.func_name == "PREV"
        assert r.args == ["D2", "明细表D2-2", "E100"]
        assert r.arity == 3
        assert r.profile == "standard"

    def test_prev_standard_semantic(self):
        """PREV('D2','明细表D2-2','合计行-期末余额') → standard profile."""
        r = parse_wp_formula("PREV('D2','明细表D2-2','合计行-期末余额')")
        assert r.func_name == "PREV"
        assert r.args == ["D2", "明细表D2-2", "合计行-期末余额"]
        assert r.arity == 3
        assert r.profile == "standard"


class TestParseWpFormula2Arg:
    """2-arg WP/PREV parsing (custom_flat and standard sheet-level)."""

    def test_wp_custom_flat_cell(self):
        """WP('CUST-01','B7') → custom_flat (second arg is cell address)."""
        r = parse_wp_formula("WP('CUST-01','B7')")
        assert r.func_name == "WP"
        assert r.args == ["CUST-01", "B7"]
        assert r.arity == 2
        assert r.profile == "custom_flat"

    def test_wp_standard_sheet_level(self):
        """WP('D2','明细表D2-2') → standard (sheet-level, no cell)."""
        r = parse_wp_formula("WP('D2','明细表D2-2')")
        assert r.func_name == "WP"
        assert r.args == ["D2", "明细表D2-2"]
        assert r.arity == 2
        assert r.profile == "standard"

    def test_prev_custom_flat(self):
        """PREV('CUST-01','B7') → custom_flat."""
        r = parse_wp_formula("PREV('CUST-01','B7')")
        assert r.func_name == "PREV"
        assert r.args == ["CUST-01", "B7"]
        assert r.arity == 2
        assert r.profile == "custom_flat"

    def test_prev_standard_sheet_level(self):
        """PREV('D2','明细表D2-2') → standard (sheet-level)."""
        r = parse_wp_formula("PREV('D2','明细表D2-2')")
        assert r.func_name == "PREV"
        assert r.args == ["D2", "明细表D2-2"]
        assert r.arity == 2
        assert r.profile == "standard"

    def test_wp_d2_cell_addr(self):
        """WP('D2','D2-2') → standard (D2-2 is sheet_code, not cell)."""
        r = parse_wp_formula("WP('D2','D2-2')")
        assert r.func_name == "WP"
        assert r.args == ["D2", "D2-2"]
        assert r.arity == 2
        # D2-2 contains hyphen, doesn't match ^[A-Za-z]{1,3}\d+$ so → standard
        assert r.profile == "standard"


class TestParseWpFormulaWhitespace:
    """Whitespace and formatting tolerance."""

    def test_spaces_between_args(self):
        """Spaces between arguments are tolerated."""
        r = parse_wp_formula("WP( 'D2' , '明细表D2-2' , 'E100' )")
        assert r.args == ["D2", "明细表D2-2", "E100"]
        assert r.arity == 3
        assert r.profile == "standard"

    def test_leading_trailing_whitespace(self):
        """Leading/trailing whitespace in formula_ref is stripped."""
        r = parse_wp_formula("  WP('D2','明细表D2-2','E100')  ")
        assert r.func_name == "WP"
        assert r.args == ["D2", "明细表D2-2", "E100"]

    def test_tabs_and_newlines(self):
        """Tab and newline characters are treated as whitespace."""
        r = parse_wp_formula("WP(\t'D2'\t,\n'明细表D2-2'\t,\t'E100'\n)")
        assert r.args == ["D2", "明细表D2-2", "E100"]


class TestParseWpFormulaQuotes:
    """Quote handling: single, double, mixed, escaped."""

    def test_double_quotes(self):
        """Double-quoted arguments."""
        r = parse_wp_formula('WP("D2","明细表D2-2","E100")')
        assert r.args == ["D2", "明细表D2-2", "E100"]
        assert r.arity == 3

    def test_mixed_quotes(self):
        """Mixed single and double quoted arguments."""
        r = parse_wp_formula("""WP('D2',"明细表D2-2",'E100')""")
        assert r.args == ["D2", "明细表D2-2", "E100"]

    def test_escaped_single_quote(self):
        """Escaped single quote within single-quoted string."""
        r = parse_wp_formula("WP('D2','表D2\\'s','E100')")
        assert r.args[1] == "表D2's"

    def test_escaped_backslash(self):
        """Escaped backslash within string."""
        r = parse_wp_formula("WP('D2','path\\\\name','E100')")
        assert r.args[1] == "path\\name"


class TestParseWpFormulaErrors:
    """Error conditions raise FormulaParseError."""

    def test_empty_string(self):
        with pytest.raises(FormulaParseError):
            parse_wp_formula("")

    def test_whitespace_only(self):
        with pytest.raises(FormulaParseError):
            parse_wp_formula("   ")

    def test_wrong_function(self):
        with pytest.raises(FormulaParseError):
            parse_wp_formula("TB('1001','审定数')")

    def test_one_arg(self):
        with pytest.raises(FormulaParseError):
            parse_wp_formula("WP('D2')")

    def test_four_args(self):
        with pytest.raises(FormulaParseError):
            parse_wp_formula("WP('a','b','c','d')")

    def test_unclosed_string(self):
        with pytest.raises(FormulaParseError):
            parse_wp_formula("WP('D2,'明细表D2-2','E100')")

    def test_missing_closing_paren(self):
        with pytest.raises(FormulaParseError):
            parse_wp_formula("WP('D2','明细表D2-2','E100'")

    def test_trailing_content(self):
        with pytest.raises(FormulaParseError):
            parse_wp_formula("WP('D2','明细表D2-2','E100') extra")


class TestParsedFormulaDataclass:
    """ParsedFormula dataclass properties."""

    def test_frozen(self):
        """ParsedFormula instances are immutable."""
        r = parse_wp_formula("WP('D2','明细表D2-2','E100')")
        with pytest.raises(Exception):
            r.func_name = "PREV"  # type: ignore

    def test_equality(self):
        """Same input produces equal results."""
        r1 = parse_wp_formula("WP('D2','明细表D2-2','E100')")
        r2 = parse_wp_formula("WP('D2','明细表D2-2','E100')")
        assert r1 == r2


class TestFormulaProfile:
    """FormulaProfile enum values."""

    def test_standard_value(self):
        assert FormulaProfile.STANDARD.value == "standard"

    def test_custom_flat_value(self):
        assert FormulaProfile.CUSTOM_FLAT.value == "custom_flat"
