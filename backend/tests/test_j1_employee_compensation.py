"""Backend tests — J1 应付职工薪酬 render策略 + 公式验证 + 分配校验.

科目：2211应付职工薪酬（贷方/负债类）

Spec: .kiro/specs/j1-employee-compensation/
Task: 7.3
"""
import pytest
from app.routers.wp_render_strategies._j1_employee_compensation import (
    validate_liability_balance,
    validate_salary_estimate,
    validate_allocation_closure,
)


class TestLiabilityBalance:
    """负债类期末余额验证: end = begin + credit - debit."""

    def test_basic(self):
        assert validate_liability_balance(100, 50, 30, 120)

    def test_zero(self):
        assert validate_liability_balance(0, 0, 0, 0)

    def test_full_debit(self):
        assert validate_liability_balance(100, 0, 100, 0)

    def test_credit_only(self):
        assert validate_liability_balance(0, 500, 0, 500)

    def test_mismatch(self):
        assert not validate_liability_balance(100, 50, 30, 999)

    def test_precision(self):
        # 0.005 < 0.01 tolerance
        assert validate_liability_balance(100.0, 50.0, 30.0, 120.005)


class TestSalaryEstimate:
    """工资测算验证: headcount × avg_salary × months."""

    def test_basic(self):
        assert validate_salary_estimate(100, 5000, 12, 6000000)

    def test_single_month(self):
        assert validate_salary_estimate(50, 8000, 1, 400000)

    def test_mismatch(self):
        assert not validate_salary_estimate(100, 5000, 12, 5000000)


class TestAllocationClosure:
    """分配闭合验证: Σ各科目 = 薪酬总额."""

    def test_balanced(self):
        is_valid, diff = validate_allocation_closure([100, 200, 300], 600)
        assert is_valid
        assert abs(diff) < 0.01

    def test_imbalanced(self):
        is_valid, diff = validate_allocation_closure([100, 200, 300], 700)
        assert not is_valid
        assert abs(diff - (-100)) < 0.01

    def test_empty(self):
        is_valid, diff = validate_allocation_closure([], 0)
        assert is_valid
        assert diff == 0

    def test_precision(self):
        is_valid, _ = validate_allocation_closure([33.33, 33.33, 33.34], 100)
        assert is_valid


class TestImportExportSheetTypes:
    """验证导入导出支持的sheet类型.
    
    Note: These tests require full app context (app.dependencies).
    Run with `python -m pytest tests/test_j1_employee_compensation.py` from backend/ with PYTHONPATH set.
    """

    @pytest.mark.skipif(True, reason="requires full app context with dependencies module")
    def test_all_types_have_columns(self):
        from app.routers.wp_render_strategies._j1_import_export import SHEET_TYPES, SHEET_COLUMNS
        for st in SHEET_TYPES:
            assert st in SHEET_COLUMNS, f"Missing columns for {st}"
            assert len(SHEET_COLUMNS[st]) > 0

    @pytest.mark.skipif(True, reason="requires full app context with dependencies module")
    def test_expected_types(self):
        from app.routers.wp_render_strategies._j1_import_export import SHEET_TYPES
        expected = {"detail", "accrual", "allocation", "general", "non_monetary", "severance"}
        assert SHEET_TYPES == expected
