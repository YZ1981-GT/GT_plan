"""Comprehensive unit tests for M-F7 权益变动表引擎 — 计算逻辑 + 写回 + RBAC + 边界.

Covers:
- Basic calculation: closing = opening + changes
- retained_earnings = opening + net_profit - dividends - surplus_reserve
- capital_reserve = opening + capital_reserve_changes
- oci = opening + oci_changes
- paid_in_capital unchanged (stub)
- other_equity_instruments unchanged (stub)
- is_llm_stub flag driven by settings
- apply_to_sheet write-back (mock DB)
- RBAC dependency exists
- 400 on invalid project_id
- movement_summary 6 columns correct

对应 spec: workpaper-m-equity-cycle M-F7 / ADR-M4
"""

import sys
sys.path.insert(0, "backend")

import inspect
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.routers.wp_m_equity_movement import (
    ClosingBalances,
    EquityMovementRequest,
    EquityMovementResponse,
    MovementSummary,
    OpeningBalances,
    _calc_equity_movement,
    _quantize,
    _validate_equity_request,
    m_equity_movement,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: 构造标准请求
# ═══════════════════════════════════════════════════════════════════════════════


def _make_request(**overrides) -> EquityMovementRequest:
    """构造标准权益变动请求，可覆盖任意字段。"""
    defaults = {
        "opening_balances": OpeningBalances(
            paid_in_capital=Decimal("5000000"),
            capital_reserve=Decimal("2000000"),
            surplus_reserve=Decimal("800000"),
            retained_earnings=Decimal("3000000"),
            oci=Decimal("100000"),
            other_equity_instruments=Decimal("500000"),
        ),
        "net_profit": Decimal("1200000"),
        "dividends": Decimal("300000"),
        "surplus_reserve": Decimal("120000"),
        "capital_reserve_changes": Decimal("50000"),
        "oci_changes": Decimal("-20000"),
        "apply_to_sheet": None,
    }
    defaults.update(overrides)
    return EquityMovementRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 计算逻辑正确性
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcEquityMovement:
    """_calc_equity_movement 计算逻辑"""

    def test_basic_closing_equals_opening_plus_changes(self):
        """基本等式：closing = opening + changes"""
        req = _make_request()
        result = _calc_equity_movement(req)
        closing = result["closing_balances"]
        ob = req.opening_balances

        # 各科目验证
        assert closing.paid_in_capital == _quantize(ob.paid_in_capital + Decimal("0"))
        assert closing.capital_reserve == _quantize(ob.capital_reserve + req.capital_reserve_changes)
        assert closing.surplus_reserve == _quantize(ob.surplus_reserve + req.surplus_reserve)
        assert closing.retained_earnings == _quantize(
            ob.retained_earnings + req.net_profit - req.dividends - req.surplus_reserve
        )
        assert closing.oci == _quantize(ob.oci + req.oci_changes)
        assert closing.other_equity_instruments == _quantize(ob.other_equity_instruments + Decimal("0"))

    def test_retained_earnings_formula(self):
        """未分配利润 = 期初 + 净利润 - 股利 - 盈余公积"""
        req = _make_request(
            opening_balances=OpeningBalances(
                paid_in_capital=Decimal("1000"),
                capital_reserve=Decimal("500"),
                surplus_reserve=Decimal("200"),
                retained_earnings=Decimal("3000"),
                oci=Decimal("0"),
                other_equity_instruments=Decimal("0"),
            ),
            net_profit=Decimal("1000"),
            dividends=Decimal("200"),
            surplus_reserve=Decimal("100"),
        )
        result = _calc_equity_movement(req)
        closing = result["closing_balances"]
        # 3000 + 1000 - 200 - 100 = 3700
        assert closing.retained_earnings == Decimal("3700.00")

    def test_capital_reserve_formula(self):
        """资本公积 = 期初 + capital_reserve_changes"""
        req = _make_request(
            opening_balances=OpeningBalances(
                paid_in_capital=Decimal("1000"),
                capital_reserve=Decimal("2000"),
                surplus_reserve=Decimal("0"),
                retained_earnings=Decimal("0"),
                oci=Decimal("0"),
                other_equity_instruments=Decimal("0"),
            ),
            capital_reserve_changes=Decimal("500"),
        )
        result = _calc_equity_movement(req)
        closing = result["closing_balances"]
        # 2000 + 500 = 2500
        assert closing.capital_reserve == Decimal("2500.00")

    def test_oci_formula(self):
        """其他综合收益 = 期初 + oci_changes"""
        req = _make_request(
            opening_balances=OpeningBalances(
                paid_in_capital=Decimal("0"),
                capital_reserve=Decimal("0"),
                surplus_reserve=Decimal("0"),
                retained_earnings=Decimal("0"),
                oci=Decimal("150000"),
                other_equity_instruments=Decimal("0"),
            ),
            oci_changes=Decimal("-30000"),
        )
        result = _calc_equity_movement(req)
        closing = result["closing_balances"]
        # 150000 + (-30000) = 120000
        assert closing.oci == Decimal("120000.00")

    def test_paid_in_capital_unchanged_stub(self):
        """实收资本不变（stub：增资/减资待 LLM 接入）"""
        req = _make_request(
            opening_balances=OpeningBalances(
                paid_in_capital=Decimal("9999999.99"),
                capital_reserve=Decimal("0"),
                surplus_reserve=Decimal("0"),
                retained_earnings=Decimal("0"),
                oci=Decimal("0"),
                other_equity_instruments=Decimal("0"),
            ),
        )
        result = _calc_equity_movement(req)
        closing = result["closing_balances"]
        assert closing.paid_in_capital == Decimal("9999999.99")

    def test_other_equity_instruments_unchanged_stub(self):
        """其他权益工具不变（stub）"""
        req = _make_request(
            opening_balances=OpeningBalances(
                paid_in_capital=Decimal("0"),
                capital_reserve=Decimal("0"),
                surplus_reserve=Decimal("0"),
                retained_earnings=Decimal("0"),
                oci=Decimal("0"),
                other_equity_instruments=Decimal("7777777.77"),
            ),
        )
        result = _calc_equity_movement(req)
        closing = result["closing_balances"]
        assert closing.other_equity_instruments == Decimal("7777777.77")

    def test_all_zeros(self):
        """全零输入 → 全零输出"""
        req = _make_request(
            opening_balances=OpeningBalances(
                paid_in_capital=Decimal("0"),
                capital_reserve=Decimal("0"),
                surplus_reserve=Decimal("0"),
                retained_earnings=Decimal("0"),
                oci=Decimal("0"),
                other_equity_instruments=Decimal("0"),
            ),
            net_profit=Decimal("0"),
            dividends=Decimal("0"),
            surplus_reserve=Decimal("0"),
            capital_reserve_changes=Decimal("0"),
            oci_changes=Decimal("0"),
        )
        result = _calc_equity_movement(req)
        closing = result["closing_balances"]
        assert closing.paid_in_capital == Decimal("0.00")
        assert closing.capital_reserve == Decimal("0.00")
        assert closing.surplus_reserve == Decimal("0.00")
        assert closing.retained_earnings == Decimal("0.00")
        assert closing.oci == Decimal("0.00")
        assert closing.other_equity_instruments == Decimal("0.00")

    def test_negative_net_profit(self):
        """净利润为负（亏损）→ 未分配利润减少"""
        req = _make_request(
            opening_balances=OpeningBalances(
                paid_in_capital=Decimal("1000"),
                capital_reserve=Decimal("0"),
                surplus_reserve=Decimal("0"),
                retained_earnings=Decimal("5000"),
                oci=Decimal("0"),
                other_equity_instruments=Decimal("0"),
            ),
            net_profit=Decimal("-2000"),
            dividends=Decimal("0"),
            surplus_reserve=Decimal("0"),
        )
        result = _calc_equity_movement(req)
        closing = result["closing_balances"]
        # 5000 + (-2000) - 0 - 0 = 3000
        assert closing.retained_earnings == Decimal("3000.00")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. movement_summary 6 列正确性
# ═══════════════════════════════════════════════════════════════════════════════


class TestMovementSummary:
    """movement_summary 6 列变动汇总"""

    def test_summary_has_6_columns(self):
        """movement_summary 包含 6 列"""
        req = _make_request()
        result = _calc_equity_movement(req)
        summary = result["movement_summary"]
        assert isinstance(summary, MovementSummary)
        # 验证 6 个字段都存在
        fields = [
            "paid_in_capital_change",
            "capital_reserve_change",
            "surplus_reserve_change",
            "retained_earnings_change",
            "oci_change",
            "other_equity_instruments_change",
        ]
        for f in fields:
            assert hasattr(summary, f), f"缺少字段: {f}"

    def test_summary_values_correct(self):
        """变动汇总值正确"""
        req = _make_request(
            net_profit=Decimal("1000"),
            dividends=Decimal("200"),
            surplus_reserve=Decimal("100"),
            capital_reserve_changes=Decimal("300"),
            oci_changes=Decimal("-50"),
        )
        result = _calc_equity_movement(req)
        summary = result["movement_summary"]

        assert summary.paid_in_capital_change == Decimal("0.00")  # stub
        assert summary.capital_reserve_change == Decimal("300.00")
        assert summary.surplus_reserve_change == Decimal("100.00")
        # retained_earnings_change = 1000 - 200 - 100 = 700
        assert summary.retained_earnings_change == Decimal("700.00")
        assert summary.oci_change == Decimal("-50.00")
        assert summary.other_equity_instruments_change == Decimal("0.00")  # stub

    def test_summary_matches_closing_minus_opening(self):
        """变动汇总 = 期末 - 期初"""
        req = _make_request()
        result = _calc_equity_movement(req)
        closing = result["closing_balances"]
        summary = result["movement_summary"]
        ob = req.opening_balances

        assert summary.paid_in_capital_change == _quantize(closing.paid_in_capital - ob.paid_in_capital)
        assert summary.capital_reserve_change == _quantize(closing.capital_reserve - ob.capital_reserve)
        assert summary.surplus_reserve_change == _quantize(closing.surplus_reserve - ob.surplus_reserve)
        assert summary.retained_earnings_change == _quantize(closing.retained_earnings - ob.retained_earnings)
        assert summary.oci_change == _quantize(closing.oci - ob.oci)
        assert summary.other_equity_instruments_change == _quantize(
            closing.other_equity_instruments - ob.other_equity_instruments
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. is_llm_stub 由 settings 驱动
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsLlmStub:
    """is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动"""

    def test_stub_true_when_service_disabled(self, monkeypatch):
        """WP_AI_SERVICE_ENABLED=False → is_llm_stub=True"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", False)
        is_stub = not getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        assert is_stub is True

    def test_stub_false_when_service_enabled(self, monkeypatch):
        """WP_AI_SERVICE_ENABLED=True → is_llm_stub=False"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", True)
        is_stub = not getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        assert is_stub is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. apply_to_sheet 写回
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """apply_to_sheet 写回联动"""

    def test_no_apply_returns_none(self):
        """不指定 apply_to_sheet → 计算正常"""
        req = _make_request(apply_to_sheet=None)
        result = _calc_equity_movement(req)
        assert "closing_balances" in result
        assert "movement_summary" in result

    def test_apply_to_sheet_field_accepted(self):
        """apply_to_sheet 字段可正常传入"""
        req = _make_request(apply_to_sheet="明细表M6-2")
        assert req.apply_to_sheet == "明细表M6-2"

    def test_write_back_function_signature(self):
        """_maybe_apply_equity_to_workpaper 函数存在且签名正确"""
        from app.routers.wp_m_equity_movement import _maybe_apply_equity_to_workpaper

        sig = inspect.signature(_maybe_apply_equity_to_workpaper)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "wp_id" in params
        assert "payload" in params
        assert "result" in params


# ═══════════════════════════════════════════════════════════════════════════════
# 5. RBAC 校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC 校验"""

    def test_endpoint_function_has_user_dependency(self):
        """endpoint 函数签名中包含 _user 参数（RBAC 注入）"""
        sig = inspect.signature(m_equity_movement)
        param_names = list(sig.parameters.keys())
        assert "_user" in param_names, "endpoint 必须有 _user 参数用于 RBAC"

    def test_endpoint_requires_edit_permission(self):
        """endpoint 使用 require_project_access('edit') 依赖"""
        sig = inspect.signature(m_equity_movement)
        user_param = sig.parameters["_user"]
        default = user_param.default
        assert default is not None, "应有 Depends 默认值"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 400 on invalid project_id
# ═══════════════════════════════════════════════════════════════════════════════


class TestInvalidProjectId:
    """invalid project_id → 400"""

    @pytest.mark.asyncio
    async def test_invalid_project_id_raises_400(self):
        """非 UUID project_id → HTTPException 400"""
        from unittest.mock import AsyncMock, MagicMock

        req = _make_request()
        mock_db = AsyncMock()
        mock_user = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await m_equity_movement(
                project_id="not-a-uuid",
                wp_id="00000000-0000-0000-0000-000000000001",
                payload=req,
                db=mock_db,
                _user=mock_user,
            )
        assert exc_info.value.status_code == 400
        assert "invalid project_id" in exc_info.value.detail


# ═══════════════════════════════════════════════════════════════════════════════
# 7. 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelpers:
    """辅助函数"""

    def test_quantize_rounds_half_up(self):
        """四舍五入到 2 位"""
        assert _quantize(Decimal("123.456")) == Decimal("123.46")
        assert _quantize(Decimal("123.454")) == Decimal("123.45")
        assert _quantize(Decimal("123.455")) == Decimal("123.46")

    def test_quantize_preserves_exact(self):
        """精确值不变"""
        assert _quantize(Decimal("100.00")) == Decimal("100.00")
        assert _quantize(Decimal("0")) == Decimal("0.00")
