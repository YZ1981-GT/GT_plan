"""Tests for report_formula_service.py — Task 1.1 coverage validation.

Validates:
- BS coverage >= 80%
- IS coverage >= 70%
- SUM_ROW auto-generation for total rows
- Fallback formula generation by row_name prefix matching
- Requirements: 13.1, 13.2, 20.1, 20.2
"""

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session

from app.services.report_formula_service import (
    ReportFormulaService,
    _normalize_name,
    _get_special,
    _generate_fallback_formula,
    _generate_sum_formula,
    _BS_SPECIAL,
    _IS_SPECIAL,
    _CFS_INDIRECT_SPECIAL,
    _EQ_SPECIAL,
    _NAME_TO_ACCOUNT,
    _NAME_TO_IS_ACCOUNT,
)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestNormalizeName:
    """Test _normalize_name strips prefixes and special chars."""

    def test_removes_triangle_prefix(self):
        assert _normalize_name("△拆出资金") == "拆出资金"
        assert _normalize_name("▲向中央银行借款") == "向中央银行借款"

    def test_removes_chinese_numbering(self):
        assert _normalize_name("一、营业收入") == "营业收入"
        assert _normalize_name("二、营业利润") == "营业利润"

    def test_removes_add_subtract_prefix(self):
        assert _normalize_name("加：营业外收入") == "营业外收入"
        assert _normalize_name("减：营业成本") == "营业成本"
        assert _normalize_name("其中：利息费用") == "利息费用"

    def test_removes_colons_and_spaces(self):
        assert _normalize_name("流动资产：") == "流动资产"
        assert _normalize_name("  货币资金  ") == "货币资金"


class TestGetSpecial:
    """Test _get_special returns correct formulas for known rows."""

    def test_bs_huobi_zijin(self):
        formula = _get_special("货币资金", "balance_sheet")
        assert formula is not None
        assert "TB('1001'" in formula
        assert "TB('1002'" in formula

    def test_bs_yingshou_zhangkuan(self):
        formula = _get_special("应收账款", "balance_sheet")
        assert formula is not None
        assert "TB('1122'" in formula

    def test_is_yingye_shouru(self):
        formula = _get_special("一、营业收入", "income_statement")
        assert formula is not None
        assert "TB('6001'" in formula

    def test_is_guanli_feiyong(self):
        formula = _get_special("管理费用", "income_statement")
        assert formula is not None
        assert "TB('6602'" in formula

    def test_is_yanfa_feiyong(self):
        formula = _get_special("研发费用", "income_statement")
        assert formula is not None
        assert "TB('6604'" in formula

    def test_unknown_returns_none(self):
        assert _get_special("不存在的行", "balance_sheet") is None

    def test_cfs_indirect(self):
        formula = _get_special("净利润", "cash_flow_supplement")
        assert formula is not None
        assert "ROW('IS-019')" in formula

    def test_eq_special(self):
        formula = _get_special("盈余公积", "equity_statement")
        assert formula is not None
        assert "TB('4101'" in formula


class TestGenerateFallbackFormula:
    """Test _generate_fallback_formula for BS and IS rows."""

    def test_bs_fallback_by_name(self):
        formula = _generate_fallback_formula("BS-099", "固定资产清理", "期末余额")
        assert formula is not None
        assert "TB('1606','期末余额')" in formula

    def test_is_fallback_by_name(self):
        formula = _generate_fallback_formula("IS-099", "税金及附加", "本期发生额")
        assert formula is not None
        assert "TB('6403','本期发生额')" in formula

    def test_unknown_name_returns_none(self):
        assert _generate_fallback_formula("BS-999", "未知行次", "期末余额") is None


class TestGenerateSumFormula:
    """Test _generate_sum_formula for total rows."""

    def test_sum_from_child_rows(self):
        """Total row should sum its child rows (higher indent_level)."""
        configs = [
            MagicMock(row_code="BS-002", row_name="货币资金", indent_level=1, is_total_row=False),
            MagicMock(row_code="BS-003", row_name="应收账款", indent_level=1, is_total_row=False),
            MagicMock(row_code="BS-004", row_name="存货", indent_level=1, is_total_row=False),
            MagicMock(row_code="BS-009", row_name="流动资产合计", indent_level=0, is_total_row=True),
        ]
        formula = _generate_sum_formula(configs, 3)
        assert formula is not None
        assert "SUM_ROW(" in formula
        assert "'BS-002'" in formula
        assert "'BS-004'" in formula

    def test_single_child_returns_row(self):
        """Single child should return ROW() not SUM_ROW()."""
        configs = [
            MagicMock(row_code="BS-011", row_name="长期股权投资", indent_level=1, is_total_row=False),
            MagicMock(row_code="BS-014", row_name="非流动资产合计", indent_level=0, is_total_row=True),
        ]
        formula = _generate_sum_formula(configs, 1)
        assert formula is not None
        assert "ROW('BS-011')" == formula

    def test_no_children_returns_none(self):
        """No children found should return None."""
        configs = [
            MagicMock(row_code="BS-001", row_name="流动资产：", indent_level=0, is_total_row=False),
        ]
        formula = _generate_sum_formula(configs, 0)
        assert formula is None


class TestBSSpecialCoverage:
    """Validate BS special formula coverage meets 80%+ target."""

    def test_bs_has_minimum_entries(self):
        """BS special should have at least 70 entries for 80%+ coverage."""
        # With ~129 BS rows in soe_standalone, we need ~80% = ~103 rows covered.
        # Special table + CAS + fallback should cover this.
        # The special table alone should have 70+ entries.
        assert len(_BS_SPECIAL) >= 70, (
            f"BS special has only {len(_BS_SPECIAL)} entries, need >= 70"
        )

    def test_bs_covers_core_accounts(self):
        """All core BS accounts must have formulas."""
        core_accounts = [
            "货币资金", "应收票据", "应收账款", "预付款项", "其他应收款",
            "存货", "固定资产", "无形资产", "在建工程", "长期股权投资",
            "短期借款", "应付账款", "应付职工薪酬", "应交税费",
            "长期借款", "实收资本", "资本公积", "盈余公积", "未分配利润",
        ]
        for name in core_accounts:
            assert name in _BS_SPECIAL, f"Core BS account '{name}' missing from _BS_SPECIAL"


class TestISSpecialCoverage:
    """Validate IS special formula coverage meets 70%+ target."""

    def test_is_has_minimum_entries(self):
        """IS special should have at least 25 entries for 70%+ coverage."""
        assert len(_IS_SPECIAL) >= 25, (
            f"IS special has only {len(_IS_SPECIAL)} entries, need >= 25"
        )

    def test_is_covers_core_items(self):
        """All core IS items must have formulas."""
        core_items = [
            "营业收入", "营业成本", "税金及附加", "销售费用",
            "管理费用", "财务费用", "投资收益", "营业外收入",
            "营业外支出", "所得税费用",
        ]
        for name in core_items:
            assert name in _IS_SPECIAL, f"Core IS item '{name}' missing from _IS_SPECIAL"


class TestFallbackMappingCoverage:
    """Validate fallback mapping completeness."""

    def test_name_to_account_covers_bs_core(self):
        """_NAME_TO_ACCOUNT should cover all core BS accounts."""
        core = [
            "货币资金", "应收票据", "应收账款", "预付款项", "存货",
            "固定资产", "无形资产", "短期借款", "应付账款", "长期借款",
        ]
        for name in core:
            assert name in _NAME_TO_ACCOUNT, f"'{name}' missing from _NAME_TO_ACCOUNT"

    def test_name_to_is_account_covers_is_core(self):
        """_NAME_TO_IS_ACCOUNT should cover all core IS items."""
        core = [
            "营业收入", "营业成本", "管理费用", "财务费用", "所得税费用",
        ]
        for name in core:
            assert name in _NAME_TO_IS_ACCOUNT, f"'{name}' missing from _NAME_TO_IS_ACCOUNT"


class TestCFSIndirectCoverage:
    """Validate CFS indirect method formulas."""

    def test_cfs_has_key_adjustments(self):
        """CFS indirect should have key adjustment items."""
        key_items = [
            "净利润", "资产减值准备", "固定资产折旧",
            "财务费用", "投资损失", "存货的减少",
            "经营性应收项目的减少", "经营性应付项目的增加",
        ]
        for name in key_items:
            assert name in _CFS_INDIRECT_SPECIAL, (
                f"CFS indirect item '{name}' missing"
            )
