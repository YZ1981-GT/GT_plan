"""_infer_category 分类推断单元测试（守护试算 category 错配修复）.

根因：account_chart.category 错配导致试算平衡假性不平（试算差额"44M"）。
本测试守护两个已修 bug + 名称优先 + 编码兜底的核心契约。
"""
from __future__ import annotations

import pytest

from app.models.audit_platform_models import AccountCategory
from app.services.account_chart_service import _infer_category


def _cat(code: str, name: str = "") -> str:
    r = _infer_category(code, name)
    return r.value if hasattr(r, "value") else str(r)


class TestInferCategoryFixedBugs:
    """两个已修 bug 的回归守护。"""

    def test_4301_special_reserve_is_equity(self):
        """Bug1: 4301 专项储备（实务权益科目）不应被成本白名单误判 expense。"""
        assert _cat("4301", "专项储备") == AccountCategory.equity.value

    def test_4301_rd_expense_still_expense(self):
        """对照：标准体系 4301 研发支出仍判 expense（编码兜底）。"""
        assert _cat("4301", "研发支出") == AccountCategory.expense.value

    def test_forex_gain_loss_subaccount_is_expense(self):
        """Bug2: 财务费用_汇兑损益（财务费用子项）不应被"汇兑损益"关键词误判 revenue。"""
        assert _cat("6603.04", "财务费用_汇兑损益") == AccountCategory.expense.value
        assert _cat("6603", "财务费用") == AccountCategory.expense.value

    def test_asset_side_equity_keyword_not_misclassified(self):
        """Bug3: 资产侧科目名含权益关键词（其他权益工具投资/长期股权投资_其他综合收益）
        不应被误判 equity——1xxx 编码优先拦截。"""
        assert _cat("1507", "其他权益工具投资") == AccountCategory.asset.value
        assert _cat("1511.04.01", "长期股权投资_其他权益变动_属于其他综合收益") == AccountCategory.asset.value
        # 负债侧同理
        assert _cat("2203", "预收账款") == AccountCategory.liability.value


class TestInferCategoryEquityVsCost:
    """4xxx 双体系：实务权益 vs 标准成本，靠名称区分。"""

    @pytest.mark.parametrize("code,name", [
        ("4001", "实收资本"),
        ("4002", "资本公积"),
        ("4003", "其他综合收益"),
        ("4011", "合伙人缴入资本"),
        ("4101", "盈余公积"),
        ("4104", "利润分配"),
        ("4201", "库存股"),
        ("4401", "其他权益工具"),
    ])
    def test_practical_equity_accounts(self, code, name):
        assert _cat(code, name) == AccountCategory.equity.value

    @pytest.mark.parametrize("code,name", [
        ("4001", "生产成本"),
        ("4101", "制造费用"),
        ("4401", "工程施工"),
    ])
    def test_standard_cost_accounts(self, code, name):
        assert _cat(code, name) == AccountCategory.expense.value


class TestInferCategory6xxxIncome:
    """6xxx 损益类：收入 vs 费用按编码 64 边界 + 名称。"""

    @pytest.mark.parametrize("code,name", [
        ("6001", "营业收入"),
        ("6111", "投资收益"),
        ("6117", "其他收益"),
        ("6301", "营业外收入"),
    ])
    def test_6xxx_revenue(self, code, name):
        assert _cat(code, name) == AccountCategory.revenue.value

    @pytest.mark.parametrize("code,name", [
        ("6401", "营业成本"),
        ("6403", "税金及附加"),
        ("6601", "销售费用"),
        ("6602", "管理费用"),
        ("6603", "财务费用"),
        ("6801", "所得税费用"),
    ])
    def test_6xxx_expense(self, code, name):
        assert _cat(code, name) == AccountCategory.expense.value


class TestInferCategoryBasics:
    """基础编码兜底。"""

    @pytest.mark.parametrize("code,expect", [
        ("1001", AccountCategory.asset.value),
        ("2001", AccountCategory.liability.value),
        ("3201", AccountCategory.equity.value),
    ])
    def test_prefix_fallback(self, code, expect):
        assert _cat(code, "") == expect
