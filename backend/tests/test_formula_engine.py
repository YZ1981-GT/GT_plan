"""统一公式引擎单元测试"""
import pytest
from decimal import Decimal
from app.services.formula_engine import execute, FormulaContext, validate_formula, execute_formula


class TestFormulaEngine:
    """核心公式执行测试"""

    def test_tb_single(self):
        ctx = FormulaContext.from_simple_map({'1002': Decimal('100000')})
        r = execute("TB('1002','期末余额')", ctx)
        assert r.value == Decimal('100000')
        assert r.ok

    def test_tb_addition(self):
        ctx = FormulaContext.from_simple_map({'1002': Decimal('100000'), '1012': Decimal('50000')})
        r = execute("TB('1002','期末余额')+TB('1012','期末余额')", ctx)
        assert r.value == Decimal('150000')
        assert len(r.trace) == 2

    def test_tb_subtraction_contra(self):
        """备抵扣减：应收账款 - 坏账准备"""
        ctx = FormulaContext.from_simple_map({'1122': Decimal('500000'), '1231': Decimal('-30000')})
        r = execute("TB('1122','期末余额')-TB('1231','期末余额')", ctx)
        assert r.value == Decimal('530000')

    def test_sum_tb_range(self):
        ctx = FormulaContext.from_simple_map({'1401': Decimal('10000'), '1406': Decimal('20000'), '1411': Decimal('5000')})
        r = execute("SUM_TB('1400~1499','期末余额')", ctx)
        assert r.value == Decimal('35000')

    def test_sum_tb_prefix_safety(self):
        """短编码不应被范围匹配"""
        ctx = FormulaContext.from_simple_map({'14': Decimal('999'), '1401': Decimal('100'), '1499': Decimal('200')})
        r = execute("SUM_TB('1400~1499','期末余额')", ctx)
        assert r.value == Decimal('300')  # 不含 '14'

    def test_row_reference(self):
        ctx = FormulaContext.from_simple_map({})
        ctx.row_cache = {'BS-027': Decimal('1000000')}
        r = execute("ROW('BS-027')", ctx)
        assert r.value == Decimal('1000000')

    def test_sum_row(self):
        ctx = FormulaContext.from_simple_map({})
        ctx.row_cache = {'BS-002': Decimal('100'), 'BS-003': Decimal('200'), 'BS-004': Decimal('300'), 'BS-010': Decimal('50')}
        r = execute("SUM_ROW('BS-002','BS-008')", ctx)
        assert r.value == Decimal('600')

    def test_prev_no_data(self):
        ctx = FormulaContext.from_simple_map({'1002': Decimal('100')})
        r = execute("PREV('1002','期末余额')", ctx)
        assert r.value == Decimal('0')
        assert len(r.warnings) == 1

    def test_prev_with_data(self):
        ctx = FormulaContext.from_simple_map({'1002': Decimal('100')}, prior_map={'1002': Decimal('80')})
        r = execute("PREV('1002','期末余额')", ctx)
        assert r.value == Decimal('80')
        assert len(r.warnings) == 0

    def test_complex_expression(self):
        ctx = FormulaContext.from_simple_map({'1002': Decimal('100')})
        r = execute("TB('1002','期末余额')*2+50", ctx)
        assert r.value == Decimal('250')

    def test_empty_formula(self):
        ctx = FormulaContext.from_simple_map({})
        r = execute("", ctx)
        assert r.value == Decimal('0')
        assert r.ok

    def test_missing_account(self):
        ctx = FormulaContext.from_simple_map({})
        r = execute("TB('9999','期末余额')", ctx)
        assert r.value == Decimal('0')
        assert r.ok  # 不报错，只是值为 0


class TestValidateFormula:
    """公式校验测试"""

    def test_valid(self):
        assert validate_formula("TB('1002','期末余额')") == []

    def test_unmatched_paren(self):
        errs = validate_formula("TB('1002','期末余额'")
        assert any("括号" in e for e in errs)

    def test_unknown_function(self):
        errs = validate_formula("UNKNOWN('x')+TB('1002','期末余额')")
        assert any("UNKNOWN" in e for e in errs)


class TestBackwardCompat:
    """向后兼容接口测试"""

    def test_execute_formula_simple(self):
        result = execute_formula("TB('1002','期末余额')", {'1002': Decimal('500')}, {})
        assert result == Decimal('500')
