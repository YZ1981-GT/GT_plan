"""CF 核查 PBT: 勾稽恒等（随机 TB → 期末-期初=净增加）

Task 3.7: 验证 reconcile_bs_cf 中的勾稽公式恒等性
- 若 BS期末 - BS期初 == CF净增加，则 bs_pass=True
- 若 经营+投资+筹资+汇率 == CF净增加，则 activity_pass=True
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.cash_flow_verification_service import CashFlowVerificationService

# 金额策略：合理范围内的 Decimal
amount_st = st.decimals(min_value=-10_000_000, max_value=10_000_000, places=2, allow_nan=False, allow_infinity=False)


@settings(max_examples=5)
@given(
    bs_end=amount_st,
    bs_begin=amount_st,
)
@pytest.mark.asyncio
async def test_bs_cf_reconcile_identity(bs_end: Decimal, bs_begin: Decimal):
    """恒等：若 CF净增加 == BS期末-期初，则 bs_pass 必为 True"""
    cf_net = bs_end - bs_begin  # 让它恒等

    db = AsyncMock()
    svc = CashFlowVerificationService(db)

    async def mock_report(pid, year, rtype, row_code, period="end"):
        mapping = {
            ("balance_sheet", "BS-002", "end"): bs_end,
            ("balance_sheet", "BS-002", "begin"): bs_begin,
            ("cash_flow_statement", "CFS-061"): cf_net,
            ("cash_flow_statement", "CFS-033"): cf_net,
            ("cash_flow_statement", "CFS-047"): Decimal("0"),
            ("cash_flow_statement", "CFS-059"): Decimal("0"),
            ("cash_flow_statement", "CFS-060"): Decimal("0"),
        }
        key = (rtype, row_code, period) if rtype == "balance_sheet" else (rtype, row_code)
        return mapping.get(key, Decimal("0"))

    svc._get_report_amount = mock_report
    svc._save_result = AsyncMock()

    result = await svc.reconcile_bs_cf(uuid4(), 2025)
    assert result["bs_pass"] is True
    assert result["bs_diff"] == Decimal("0")


@settings(max_examples=5)
@given(
    operating=amount_st,
    investing=amount_st,
    financing=amount_st,
    exchange=amount_st,
)
@pytest.mark.asyncio
async def test_activity_sum_identity(operating: Decimal, investing: Decimal, financing: Decimal, exchange: Decimal):
    """恒等：若 CF净增加 == 经营+投资+筹资+汇率，则 activity_pass 必为 True"""
    cf_net = operating + investing + financing + exchange

    db = AsyncMock()
    svc = CashFlowVerificationService(db)

    async def mock_report(pid, year, rtype, row_code, period="end"):
        mapping = {
            ("balance_sheet", "BS-002", "end"): cf_net,
            ("balance_sheet", "BS-002", "begin"): Decimal("0"),
            ("cash_flow_statement", "CFS-061"): cf_net,
            ("cash_flow_statement", "CFS-033"): operating,
            ("cash_flow_statement", "CFS-047"): investing,
            ("cash_flow_statement", "CFS-059"): financing,
            ("cash_flow_statement", "CFS-060"): exchange,
        }
        key = (rtype, row_code, period) if rtype == "balance_sheet" else (rtype, row_code)
        return mapping.get(key, Decimal("0"))

    svc._get_report_amount = mock_report
    svc._save_result = AsyncMock()

    result = await svc.reconcile_bs_cf(uuid4(), 2025)
    assert result["activity_pass"] is True
    assert result["activity_diff"] == Decimal("0")


@settings(max_examples=5)
@given(
    bs_end=amount_st,
    bs_begin=amount_st,
    delta=st.decimals(min_value=Decimal("0.02"), max_value=1000000, places=2, allow_nan=False, allow_infinity=False),
)
@pytest.mark.asyncio
async def test_bs_cf_reconcile_fail_on_mismatch(bs_end: Decimal, bs_begin: Decimal, delta: Decimal):
    """反面：若 CF净增加 != BS期末-期初（差额>0.01），则 bs_pass 必为 False"""
    cf_net = bs_end - bs_begin + delta  # 故意不等

    db = AsyncMock()
    svc = CashFlowVerificationService(db)

    async def mock_report(pid, year, rtype, row_code, period="end"):
        mapping = {
            ("balance_sheet", "BS-002", "end"): bs_end,
            ("balance_sheet", "BS-002", "begin"): bs_begin,
            ("cash_flow_statement", "CFS-061"): cf_net,
            ("cash_flow_statement", "CFS-033"): cf_net,
            ("cash_flow_statement", "CFS-047"): Decimal("0"),
            ("cash_flow_statement", "CFS-059"): Decimal("0"),
            ("cash_flow_statement", "CFS-060"): Decimal("0"),
        }
        key = (rtype, row_code, period) if rtype == "balance_sheet" else (rtype, row_code)
        return mapping.get(key, Decimal("0"))

    svc._get_report_amount = mock_report
    svc._save_result = AsyncMock()

    result = await svc.reconcile_bs_cf(uuid4(), 2025)
    assert result["bs_pass"] is False
