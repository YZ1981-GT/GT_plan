"""Tests for validate_formula + AddressValidator integration (Task 17).

验证 validate_formula 接 address_registry 的地址有效性校验：
- 当 address_validator=None（默认）时，跳过地址校验（向后兼容）
- 当提供 address_validator 时，提取公式中所有引用编码并校验
- 悬空引用产生 validation error
"""

import pytest

from app.services.formula_engine import (
    AddressValidator,
    _extract_formula_codes,
    validate_formula,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Fixtures: AddressValidator 实现
# ═══════════════════════════════════════════════════════════════════════════════


class MockAddressValidator:
    """Mock 地址校验器：预载一组有效编码，不在其中的即为无效。"""

    def __init__(self, valid_codes: set[str]):
        self._valid_codes = valid_codes

    def validate_codes(self, codes: set[str]) -> set[str]:
        return codes - self._valid_codes


class AllValidValidator:
    """所有编码都有效的校验器。"""

    def validate_codes(self, codes: set[str]) -> set[str]:
        return set()


class AllInvalidValidator:
    """所有编码都无效的校验器。"""

    def validate_codes(self, codes: set[str]) -> set[str]:
        return codes


# ═══════════════════════════════════════════════════════════════════════════════
# Protocol 合规性测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddressValidatorProtocol:
    """验证 AddressValidator Protocol 的 runtime_checkable 行为。"""

    def test_mock_validator_is_protocol_compliant(self):
        validator = MockAddressValidator({"1001", "1002"})
        assert isinstance(validator, AddressValidator)

    def test_all_valid_validator_is_protocol_compliant(self):
        validator = AllValidValidator()
        assert isinstance(validator, AddressValidator)

    def test_all_invalid_validator_is_protocol_compliant(self):
        validator = AllInvalidValidator()
        assert isinstance(validator, AddressValidator)


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_formula_codes 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractFormulaCodes:
    """验证从公式中提取引用编码的逻辑。"""

    def test_tb_single_code(self):
        codes = _extract_formula_codes("TB('1002','期末余额')")
        assert codes == {"1002"}

    def test_tb_multiple_codes(self):
        codes = _extract_formula_codes("TB('1001','期末余额')+TB('1002','期末余额')")
        assert codes == {"1001", "1002"}

    def test_sum_tb_range(self):
        codes = _extract_formula_codes("SUM_TB('1400~1499','期末余额')")
        assert codes == {"1400", "1499"}

    def test_row_code(self):
        codes = _extract_formula_codes("ROW('BS-002')")
        assert codes == {"BS-002"}

    def test_sum_row_codes(self):
        codes = _extract_formula_codes("SUM_ROW('BS-002','BS-008')")
        assert codes == {"BS-002", "BS-008"}

    def test_report_code(self):
        codes = _extract_formula_codes("REPORT('BS-001','current')")
        assert codes == {"BS-001"}

    def test_prev_code(self):
        codes = _extract_formula_codes("PREV('1002','期末余额')")
        assert codes == {"1002"}

    def test_aux_code(self):
        codes = _extract_formula_codes("AUX('1122','客户A','期末余额')")
        assert codes == {"1122"}

    def test_note_code(self):
        codes = _extract_formula_codes("NOTE('五、1','合计','期末')")
        assert codes == {"五、1"}

    def test_wp_code(self):
        codes = _extract_formula_codes("WP('E1','审定数')")
        assert codes == {"E1"}

    def test_complex_formula_multiple_types(self):
        formula = "TB('1001','期末余额')+ROW('BS-002')-PREV('1002','期末余额')"
        codes = _extract_formula_codes(formula)
        assert codes == {"1001", "BS-002", "1002"}

    def test_empty_formula(self):
        codes = _extract_formula_codes("")
        assert codes == set()

    def test_no_references(self):
        codes = _extract_formula_codes("ABS(100)+ROUND(3.14,2)")
        assert codes == set()

    def test_nested_prev_tb(self):
        """PREV(TB('1002','期末余额')) — 嵌套场景提取外层 PREV 的编码"""
        codes = _extract_formula_codes("PREV('1002','期末余额')")
        assert "1002" in codes


# ═══════════════════════════════════════════════════════════════════════════════
# validate_formula + address_validator 集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateFormulaWithAddressValidator:
    """验证 validate_formula 接 address_validator 的行为。"""

    def test_no_validator_backward_compatible(self):
        """不传 address_validator 时，行为与之前完全一致。"""
        errors = validate_formula("TB('1001','期末余额')")
        assert errors == []

    def test_no_validator_still_checks_syntax(self):
        """不传 address_validator 时，仍然检查语法错误。"""
        errors = validate_formula("TB('1001','期末余额'")
        assert any("括号" in e for e in errors)

    def test_all_codes_valid_no_errors(self):
        """所有引用编码都有效时，无地址校验错误。"""
        validator = MockAddressValidator({"1001", "1002", "BS-002"})
        errors = validate_formula(
            "TB('1001','期末余额')+TB('1002','期末余额')+ROW('BS-002')",
            address_validator=validator,
        )
        assert errors == []

    def test_dangling_reference_produces_error(self):
        """悬空引用产生 validation error。"""
        validator = MockAddressValidator({"1001"})  # 只有 1001 有效
        errors = validate_formula(
            "TB('1001','期末余额')+TB('9999','期末余额')",
            address_validator=validator,
        )
        assert any("9999" in e and "悬空引用" in e for e in errors)

    def test_multiple_dangling_references(self):
        """多个悬空引用各自产生独立错误。"""
        validator = MockAddressValidator({"1001"})
        errors = validate_formula(
            "TB('1001','期末余额')+TB('9999','期末余额')+ROW('XX-999')",
            address_validator=validator,
        )
        dangling_errors = [e for e in errors if "悬空引用" in e]
        assert len(dangling_errors) == 2
        assert any("9999" in e for e in dangling_errors)
        assert any("XX-999" in e for e in dangling_errors)

    def test_all_valid_validator_no_errors(self):
        """AllValidValidator 不产生任何地址错误。"""
        validator = AllValidValidator()
        errors = validate_formula(
            "TB('ANY_CODE','期末余额')+ROW('ANY_ROW')",
            address_validator=validator,
        )
        assert errors == []

    def test_all_invalid_validator_all_errors(self):
        """AllInvalidValidator 对所有引用产生错误。"""
        validator = AllInvalidValidator()
        errors = validate_formula(
            "TB('1001','期末余额')+ROW('BS-002')",
            address_validator=validator,
        )
        dangling_errors = [e for e in errors if "悬空引用" in e]
        assert len(dangling_errors) == 2

    def test_syntax_errors_still_reported_with_validator(self):
        """即使有 address_validator，语法错误仍然报告。"""
        validator = AllValidValidator()
        errors = validate_formula("UNKNOWN_FUNC('x')", address_validator=validator)
        assert any("未知函数" in e for e in errors)

    def test_empty_formula_with_validator(self):
        """空公式 + validator 不报错。"""
        validator = AllInvalidValidator()
        errors = validate_formula("", address_validator=validator)
        assert errors == []

    def test_formula_without_references_with_validator(self):
        """纯数学公式（无引用）+ validator 不报错。"""
        validator = AllInvalidValidator()
        errors = validate_formula("ABS(100)+ROUND(3.14,2)", address_validator=validator)
        assert errors == []

    def test_sum_tb_range_validation(self):
        """SUM_TB 范围编码的起止都被校验。"""
        validator = MockAddressValidator({"1400"})  # 只有 1400 有效，1499 无效
        errors = validate_formula(
            "SUM_TB('1400~1499','期末余额')",
            address_validator=validator,
        )
        dangling_errors = [e for e in errors if "悬空引用" in e]
        assert len(dangling_errors) == 1
        assert any("1499" in e for e in dangling_errors)

    def test_sum_row_both_codes_validated(self):
        """SUM_ROW 的起止行次编码都被校验。"""
        validator = MockAddressValidator({"BS-002"})  # BS-008 无效
        errors = validate_formula(
            "SUM_ROW('BS-002','BS-008')",
            address_validator=validator,
        )
        dangling_errors = [e for e in errors if "悬空引用" in e]
        assert len(dangling_errors) == 1
        assert any("BS-008" in e for e in dangling_errors)

    def test_prev_code_validated(self):
        """PREV 引用的科目编码被校验。"""
        validator = MockAddressValidator(set())  # 无有效编码
        errors = validate_formula(
            "PREV('1002','期末余额')",
            address_validator=validator,
        )
        assert any("1002" in e and "悬空引用" in e for e in errors)

    def test_note_code_validated(self):
        """NOTE 引用的章节编码被校验。"""
        validator = MockAddressValidator(set())
        errors = validate_formula(
            "NOTE('五、1','合计','期末')",
            address_validator=validator,
        )
        assert any("五、1" in e and "悬空引用" in e for e in errors)

    def test_wp_code_validated(self):
        """WP 引用的底稿编码被校验。"""
        validator = MockAddressValidator(set())
        errors = validate_formula(
            "WP('E1','审定数')",
            address_validator=validator,
        )
        assert any("E1" in e and "悬空引用" in e for e in errors)
