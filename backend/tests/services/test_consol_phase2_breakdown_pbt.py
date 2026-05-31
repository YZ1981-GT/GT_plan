"""合并模块 Phase 2 S5 报表穿透自洽 PBT（hypothesis）

`consol_report_breakdown_service.get_report_consol_breakdown` 读 Phase 0 写入的
`consol_trial.consolidation_breakdown` provenance，反查"某合并报表科目由哪些子公司
贡献多少 + 抵销 + 合并数"。本端点**只读 + 计算占比，不重算**。

属性 S5（需求 5.3）：Σ Decimal(by_company[*].amount) == individual_sum
（provenance 自洽，复用 Phase 0 P2）。本测试构造 by_company 金额之和恰等于
individual_sum 的合成 trial 行，断言返回的 by_company 金额之和守恒、占比之和约等于 1。

EH5（需求 5.4）：trial 行不存在 / breakdown 空 → has_breakdown=False + by_company=[] +
友好提示，不抛异常。

构造方式：fake ConsolTrial-like 对象 + patch `_load_trial_row` 返回它（避免真实 DB）。

Validates: Requirements 5.1, 5.2, 5.3, 5.4 (Property S5); Error scenario EH5
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, strategies as st

from app.services.consol_report_breakdown_service import (
    EMPTY_BREAKDOWN_MESSAGE,
    _safe_decimal,
    get_report_consol_breakdown,
)

_MODULE = "app.services.consol_report_breakdown_service"

# 单子公司金额：含正负，Decimal places=2
_company_amount = st.decimals(
    min_value=Decimal("-9999999.99"),
    max_value=Decimal("9999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


def _fake_trial(
    *,
    by_company: list[dict],
    individual_sum: Decimal,
    consol_elimination: Decimal = Decimal("0"),
    consol_amount: Decimal = Decimal("0"),
    breakdown_present: bool = True,
):
    """构造 ConsolTrial-like 替身（仅含 service 读取的字段）。"""
    breakdown = None
    if breakdown_present:
        breakdown = {
            "by_company": by_company,
            "individual_sum": str(individual_sum),
            "computed_at": "2026-05-30T00:00:00Z",
        }
    return SimpleNamespace(
        consolidation_breakdown=breakdown,
        individual_sum=individual_sum,
        consol_elimination=consol_elimination,
        consol_amount=consol_amount,
    )


@st.composite
def breakdown_strategy(draw: st.DrawFn):
    """生成一组子公司金额，individual_sum 设为其精确和（保证 S5 自洽前提）。"""
    n = draw(st.integers(min_value=1, max_value=6))
    amounts = draw(st.lists(_company_amount, min_size=n, max_size=n))
    by_company = [
        {
            "company_code": f"SUB{i:03d}",
            "company_name": f"子公司{i}",
            "amount": str(amt),
        }
        for i, amt in enumerate(amounts)
    ]
    individual_sum = sum(amounts, Decimal("0"))
    return by_company, individual_sum


# ===========================================================================
# 纯函数 _safe_decimal
# ===========================================================================


class TestSafeDecimal:
    """_safe_decimal 防御性解析。"""

    @given(amt=_company_amount)
    @settings(max_examples=15)
    def test_roundtrip_via_string(self, amt):
        """str(Decimal) → _safe_decimal 还原精确相等。"""
        assert _safe_decimal(str(amt)) == amt

    def test_none_and_garbage_return_zero(self):
        assert _safe_decimal(None) == Decimal("0")
        assert _safe_decimal("") == Decimal("0")
        assert _safe_decimal("not-a-number") == Decimal("0")
        assert _safe_decimal([1, 2]) == Decimal("0")


# ===========================================================================
# S5 穿透 provenance 自洽
# ===========================================================================


class TestS5BreakdownSelfConsistency:
    """S5：Σ by_company[*].amount == individual_sum；占比和约等于 1。

    **Validates: Requirements 5.3**
    """

    @given(data=breakdown_strategy())
    @settings(max_examples=15)
    @pytest.mark.asyncio
    async def test_sum_by_company_equals_individual_sum(self, data):
        """返回的 by_company 金额之和 == individual_sum（守恒）。"""
        by_company, individual_sum = data
        trial = _fake_trial(by_company=by_company, individual_sum=individual_sum)

        with patch(f"{_MODULE}._load_trial_row", new=AsyncMock(return_value=trial)):
            result = await get_report_consol_breakdown(AsyncMock(), uuid4(), 2025, "1122")

        assert result["has_breakdown"] is True
        recomputed = sum(
            (_safe_decimal(c["amount"]) for c in result["by_company"]), Decimal("0")
        )
        assert recomputed == individual_sum
        # individual_sum 原样 surface
        assert _safe_decimal(result["individual_sum"]) == individual_sum

    @given(data=breakdown_strategy())
    @settings(max_examples=15)
    @pytest.mark.asyncio
    async def test_ratios_sum_to_about_one_when_total_nonzero(self, data):
        """total != 0 时，各子公司占比之和约等于 1（4 位小数舍入容差）。"""
        by_company, individual_sum = data
        trial = _fake_trial(by_company=by_company, individual_sum=individual_sum)

        with patch(f"{_MODULE}._load_trial_row", new=AsyncMock(return_value=trial)):
            result = await get_report_consol_breakdown(AsyncMock(), uuid4(), 2025, "1122")

        total = sum((_safe_decimal(c["amount"]) for c in by_company), Decimal("0"))
        ratios_sum = sum(
            (Decimal(c["ratio"]) for c in result["by_company"]), Decimal("0")
        )
        if total != 0:
            # 每条 ratio 量化到 0.0001，N 条累计误差上界 N * 0.0001
            tolerance = Decimal("0.0001") * len(by_company)
            assert abs(ratios_sum - Decimal("1")) <= tolerance, (
                f"占比之和 {ratios_sum} 偏离 1 超过容差 {tolerance}"
            )
        else:
            # total==0 时 ratio 全为 "0"
            assert ratios_sum == Decimal("0")

    @pytest.mark.asyncio
    async def test_passes_through_elimination_and_consolidated(self):
        """穿透返回原样 surface consol_elimination / consol_amount（不重算）。"""
        by_company = [{"company_code": "S1", "company_name": "甲", "amount": "100.00"}]
        trial = _fake_trial(
            by_company=by_company,
            individual_sum=Decimal("100.00"),
            consol_elimination=Decimal("-30.00"),
            consol_amount=Decimal("70.00"),
        )
        with patch(f"{_MODULE}._load_trial_row", new=AsyncMock(return_value=trial)):
            result = await get_report_consol_breakdown(AsyncMock(), uuid4(), 2025, "1122")

        assert result["elimination"] == "-30.00"
        assert result["consolidated"] == "70.00"
        assert result["account_code"] == "1122"


# ===========================================================================
# EH5：无 breakdown 友好空返回
# ===========================================================================


class TestEH5EmptyBreakdown:
    """EH5：trial 不存在 / breakdown 空 → 友好空返回，不抛异常。

    **Validates: Requirements 5.4**
    """

    @pytest.mark.asyncio
    async def test_trial_row_none_returns_empty(self):
        """_load_trial_row 返回 None → has_breakdown=False + 空 by_company + 提示。"""
        with patch(f"{_MODULE}._load_trial_row", new=AsyncMock(return_value=None)):
            result = await get_report_consol_breakdown(AsyncMock(), uuid4(), 2025, "9999")

        assert result["has_breakdown"] is False
        assert result["by_company"] == []
        assert result["message"] == EMPTY_BREAKDOWN_MESSAGE
        # 不抛异常，且默认金额字段为 "0"
        assert result["elimination"] == "0"
        assert result["consolidated"] == "0"

    @pytest.mark.asyncio
    async def test_breakdown_present_but_no_by_company(self):
        """trial 行存在但 consolidation_breakdown=None（未跑 B1）→ 友好空返回。"""
        trial = _fake_trial(
            by_company=[],
            individual_sum=Decimal("0"),
            consol_elimination=Decimal("-5.00"),
            consol_amount=Decimal("5.00"),
            breakdown_present=False,
        )
        with patch(f"{_MODULE}._load_trial_row", new=AsyncMock(return_value=trial)):
            result = await get_report_consol_breakdown(AsyncMock(), uuid4(), 2025, "1122")

        assert result["has_breakdown"] is False
        assert result["by_company"] == []
        assert result["message"] == EMPTY_BREAKDOWN_MESSAGE
        # trial 存在 → 金额字段来自 trial（非默认 "0"）
        assert result["elimination"] == "-5.00"
        assert result["consolidated"] == "5.00"

    @pytest.mark.asyncio
    async def test_empty_by_company_list(self):
        """breakdown 存在但 by_company 是空列表 → 友好空返回。"""
        trial = _fake_trial(by_company=[], individual_sum=Decimal("0"))
        with patch(f"{_MODULE}._load_trial_row", new=AsyncMock(return_value=trial)):
            result = await get_report_consol_breakdown(AsyncMock(), uuid4(), 2025, "1122")

        assert result["has_breakdown"] is False
        assert result["by_company"] == []
