"""现金流量表核查服务单元测试（已知数据验证）

Task 3.6: 逆算公式计算正确性
Task 3.7: 勾稽恒等 PBT
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.cash_flow_verification_service import CashFlowVerificationService, _load_formulas


# ─── Task 3.6: 逆算公式单元测试 ───

class TestFormulaConfig:
    """验证公式配置文件结构正确"""

    def test_load_formulas_valid(self):
        data = _load_formulas()
        assert "operating" in data
        assert "investing" in data
        assert "financing" in data
        assert "supplementary_indirect" in data
        assert "reconciliation" in data
        assert "cash_equivalent_accounts" in data

    def test_operating_items_have_required_fields(self):
        data = _load_formulas()
        for item in data["operating"]:
            assert "item" in item
            assert "row_code" in item
            assert "formula" in item
            assert item["row_code"].startswith("CFS-")

    def test_supplementary_items_have_source(self):
        data = _load_formulas()
        for item in data["supplementary_indirect"]["items"]:
            assert "item" in item
            assert "row_code" in item
            assert "sign" in item
            assert item["sign"] in (1, -1)


class TestEvalFormula:
    """验证公式求值逻辑"""

    @pytest.fixture
    def svc(self):
        db = AsyncMock()
        return CashFlowVerificationService(db)

    def test_simple_addition(self, svc):
        result = svc._eval_formula("a + b", {"a": Decimal("100"), "b": Decimal("200")})
        assert result == Decimal("300")

    def test_subtraction(self, svc):
        result = svc._eval_formula("a - b", {"a": Decimal("500"), "b": Decimal("200")})
        assert result == Decimal("300")

    def test_complex_formula(self, svc):
        # 销售收到 = revenue + (ar_begin - ar_end) + (advance_end - advance_begin)
        values = {
            "revenue": Decimal("1000000"),
            "ar_begin": Decimal("300000"),
            "ar_end": Decimal("250000"),
            "advance_end": Decimal("80000"),
            "advance_begin": Decimal("60000"),
        }
        formula = "revenue + (ar_begin - ar_end) + (advance_end - advance_begin)"
        result = svc._eval_formula(formula, values)
        # 1000000 + (300000-250000) + (80000-60000) = 1070000
        assert result == Decimal("1070000")

    def test_zero_values(self, svc):
        result = svc._eval_formula("a + b", {"a": Decimal("0"), "b": Decimal("0")})
        assert result == Decimal("0")


class TestCashEquivalentsCalculation:
    """验证现金等价物计算逻辑"""

    @pytest.fixture
    def svc(self):
        db = AsyncMock()
        svc = CashFlowVerificationService(db)
        return svc

    @pytest.mark.asyncio
    async def test_cash_equivalents_pass(self, svc):
        """TB合计 == BS货币资金 → pass"""
        svc._get_tb_balances = AsyncMock(return_value=[
            ("1001", Decimal("50000"), Decimal("60000")),
            ("1002", Decimal("200000"), Decimal("240000")),
        ])
        svc._get_report_amount = AsyncMock(return_value=Decimal("300000"))
        svc._save_result = AsyncMock()

        result = await svc.get_cash_equivalents(uuid4(), 2025)
        assert result["total"] == Decimal("300000")
        assert result["pass"] is True
        assert result["difference"] == Decimal("0")

    @pytest.mark.asyncio
    async def test_cash_equivalents_fail(self, svc):
        """TB合计 != BS货币资金 → fail"""
        svc._get_tb_balances = AsyncMock(return_value=[
            ("1001", Decimal("50000"), Decimal("60000")),
            ("1002", Decimal("200000"), Decimal("240000")),
        ])
        svc._get_report_amount = AsyncMock(return_value=Decimal("280000"))
        svc._save_result = AsyncMock()

        result = await svc.get_cash_equivalents(uuid4(), 2025)
        assert result["total"] == Decimal("300000")
        assert result["pass"] is False
        assert result["difference"] == Decimal("20000")


class TestReconciliation:
    """验证勾稽核对逻辑"""

    @pytest.fixture
    def svc(self):
        db = AsyncMock()
        return CashFlowVerificationService(db)

    @pytest.mark.asyncio
    async def test_reconcile_pass(self, svc):
        """BS期末-期初 == CF净增加 → pass"""
        async def mock_report(pid, year, rtype, row_code, period="end"):
            mapping = {
                ("balance_sheet", "BS-002", "end"): Decimal("500000"),
                ("balance_sheet", "BS-002", "begin"): Decimal("300000"),
                ("cash_flow_statement", "CFS-061"): Decimal("200000"),
                ("cash_flow_statement", "CFS-033"): Decimal("150000"),
                ("cash_flow_statement", "CFS-047"): Decimal("30000"),
                ("cash_flow_statement", "CFS-059"): Decimal("20000"),
                ("cash_flow_statement", "CFS-060"): Decimal("0"),
            }
            key = (rtype, row_code, period) if rtype == "balance_sheet" else (rtype, row_code)
            return mapping.get(key, Decimal("0"))

        svc._get_report_amount = mock_report
        svc._save_result = AsyncMock()

        result = await svc.reconcile_bs_cf(uuid4(), 2025)
        assert result["bs_pass"] is True
        assert result["bs_diff"] == Decimal("0")
        assert result["activity_pass"] is True

    @pytest.mark.asyncio
    async def test_reconcile_fail(self, svc):
        """BS期末-期初 != CF净增加 → fail"""
        call_count = {"n": 0}

        async def mock_report(pid, year, rtype, row_code, period="end"):
            mapping = {
                ("balance_sheet", "BS-002", "end"): Decimal("500000"),
                ("balance_sheet", "BS-002", "begin"): Decimal("300000"),
                ("cash_flow_statement", "CFS-061"): Decimal("180000"),  # 差20000
                ("cash_flow_statement", "CFS-033"): Decimal("150000"),
                ("cash_flow_statement", "CFS-047"): Decimal("30000"),
                ("cash_flow_statement", "CFS-059"): Decimal("20000"),
                ("cash_flow_statement", "CFS-060"): Decimal("0"),
            }
            key = (rtype, row_code, period) if rtype == "balance_sheet" else (rtype, row_code)
            return mapping.get(key, Decimal("0"))

        svc._get_report_amount = mock_report
        svc._save_result = AsyncMock()

        result = await svc.reconcile_bs_cf(uuid4(), 2025)
        assert result["bs_pass"] is False
        assert result["bs_diff"] == Decimal("20000")
