"""F2 公式保存校验单元测试."""
from app.services.f2_extraction.validation import validate_f2_formula


def test_valid_f2_formula_saves_ok():
    assert validate_f2_formula("TB('1401','借方发生额')") is None
    assert validate_f2_formula("ABS(TB('1471','期初余额'))") is None
    assert validate_f2_formula("=TB('1406','贷方发生额')") is None


def test_invalid_column_rejected():
    error = validate_f2_formula("TB('1401','审定数')")
    assert error is not None
    assert "列名" in error or "格式" in error


def test_malformed_expression_rejected():
    error = validate_f2_formula("SUM(A1:B2)")
    assert error is not None


def test_unsupported_function_rejected():
    error = validate_f2_formula("AUX('1401','客户','期末')")
    assert error is not None
    assert "AUX" in error


def test_empty_rejected():
    error = validate_f2_formula("")
    assert error is not None
