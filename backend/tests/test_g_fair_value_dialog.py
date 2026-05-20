"""Unit tests for G-F4 公允价值测试弹窗 (Level 1/2/3) — formula correctness + validation + write-back + RBAC + config-driven stub.

Covers:
- Level 1: market_price × face_value → fair_value（活跃市场报价）
- Level 2: avg(interest_rate_curve) + credit_spread + volatility → fair_value（可观察输入）
- Level 3: DCF Σ(CF/(1+r)^i) + terminal_value/(1+r)^n → fair_value（不可观察输入）
- Validation: 各 level 必填字段缺失 → 422 / discount_rate ≤ 0 或 ≥ 1 → 400 / face_value > 1e15 → 400
- Write-back: parsed_data.fair_value_tests[sheet] 数据结构 + apply_to_sheet=None 直接返回 None
- RBAC: require_project_access("edit") 强制校验
- is_llm_stub config-driven: monkeypatch settings.WP_AI_SERVICE_ENABLED → 字段同步切换 + Level 3 conclusion 文案变化

对应 spec: workpaper-g-investment-cycle G-F4 / ADR-G3
对应 task: Sprint 2 Task 2.7
"""

from __future__ import annotations

import sys

sys.path.insert(0, "backend")

import asyncio
import inspect
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.routers.wp_g_fair_value import (
    FairValueTestRequest,
    FairValueTestResponse,
    _calc_level_1_fv,
    _calc_level_2_fv,
    _calc_level_3_fv,
    _maybe_apply_fair_value_to_workpaper,
    _quantize,
    _validate_inputs,
    g_fair_value_test,
    router,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. LEVEL 1 — 活跃市场报价（market_price × face_value）
# ═══════════════════════════════════════════════════════════════════════════════


class TestLevel1ActiveMarketPrice:
    """Level 1: 公允价值 = 市场单价 × 面值/数量"""

    def test_basic_market_price_times_face_value(self):
        """market_price=10.50 × face_value=1000 = 10500.00"""
        fv = _calc_level_1_fv(face_value=Decimal("1000"), market_price=Decimal("10.50"))
        assert fv == Decimal("10500.00")

    def test_market_price_zero_returns_zero(self):
        """market_price=0 → fair_value=0（合法但价值为 0）"""
        fv = _calc_level_1_fv(face_value=Decimal("1000"), market_price=Decimal("0"))
        assert fv == Decimal("0.00")

    def test_high_precision_quantized_to_2_decimals(self):
        """高精度结果保留 2 位小数（四舍五入 HALF_UP）"""
        fv = _calc_level_1_fv(face_value=Decimal("3"), market_price=Decimal("3.335"))
        # 3 × 3.335 = 10.005 → quantize → 10.01（HALF_UP）
        assert fv == Decimal("10.01")

    def test_endpoint_response_for_level_1(self):
        """Level 1 endpoint 返回完整字段 + 估值方法描述含 market_price"""

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = FairValueTestRequest(
                level=1,
                instrument_type="交易性金融资产",
                face_value=Decimal("1000"),
                market_price=Decimal("12.50"),
                price_date="2026-05-19",
            )
            return await g_fair_value_test(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert isinstance(resp, FairValueTestResponse)
        assert resp.level == 1
        assert resp.fair_value == "12500.00"
        assert "Level 1" in resp.valuation_method
        assert "market_price=12.50" in resp.valuation_method
        assert resp.dcf_details is None
        assert resp.applied_to_sheet is None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LEVEL 2 — 可观察输入（利率曲线 + 信用利差 + 波动率）
# ═══════════════════════════════════════════════════════════════════════════════


class TestLevel2ObservableInputs:
    """Level 2: 简化估值 = face_value × (1 - credit_spread + volatility × avg_rate)"""

    def test_zero_spread_zero_volatility_returns_face_value(self):
        """credit_spread=0 且 volatility=0 → adjustment=1 → fv=face_value"""
        fv = _calc_level_2_fv(
            face_value=Decimal("1000000"),
            interest_rate_curve=[Decimal("0.03"), Decimal("0.035"), Decimal("0.04")],
            credit_spread=Decimal("0"),
            volatility=Decimal("0"),
        )
        assert fv == Decimal("1000000.00")

    def test_credit_spread_reduces_fair_value(self):
        """credit_spread=0.05 不带 volatility → adjustment=0.95 → fv = 950000"""
        fv = _calc_level_2_fv(
            face_value=Decimal("1000000"),
            interest_rate_curve=[Decimal("0.03"), Decimal("0.035"), Decimal("0.04")],
            credit_spread=Decimal("0.05"),
            volatility=Decimal("0"),
        )
        assert fv == Decimal("950000.00")

    def test_volatility_lifts_fair_value_via_avg_rate(self):
        """volatility>0 通过 avg_rate 增加调整因子（>1）"""
        # avg = (0.03+0.035+0.04)/3 = 0.035
        # adjustment = 1 - 0 + 1.0×0.035 = 1.035
        fv = _calc_level_2_fv(
            face_value=Decimal("1000000"),
            interest_rate_curve=[Decimal("0.03"), Decimal("0.035"), Decimal("0.04")],
            credit_spread=Decimal("0"),
            volatility=Decimal("1.0"),
        )
        assert fv == Decimal("1035000.00")

    def test_extreme_credit_spread_floored_at_zero(self):
        """巨大 credit_spread 使调整因子 < 0 → cap 在 0"""
        # adjustment = 1 - 0.99 + 0×0.04 = 0.01；调小到极端值
        # 但因为 credit_spread < 1 limit，无法直接传 ≥1，用接近 1 + 0 volatility
        # 所以构造一个能产生负调整的输入：1 - 0.95 - x = ?
        # 由于 volatility ≥ 0 不能减，credit_spread < 1 不能 ≥ 1 → 实际上调整因子总 ≥ 0
        # 这里验证：极端临界 credit_spread=0.99 + volatility=0 → adjustment=0.01
        fv = _calc_level_2_fv(
            face_value=Decimal("1000000"),
            interest_rate_curve=[Decimal("0.03")],
            credit_spread=Decimal("0.99"),
            volatility=Decimal("0"),
        )
        assert fv == Decimal("10000.00")
        assert fv >= Decimal("0")

    def test_endpoint_response_for_level_2(self):
        """Level 2 endpoint 返回 valuation_method 含期数和 avg_rate"""

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = FairValueTestRequest(
                level=2,
                instrument_type="债权投资",
                face_value=Decimal("1000000"),
                interest_rate_curve=[Decimal("0.03"), Decimal("0.035"), Decimal("0.04")],
                credit_spread=Decimal("0.02"),
                volatility=Decimal("0.5"),
            )
            return await g_fair_value_test(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.level == 2
        # avg = 0.035；adjustment = 1 - 0.02 + 0.5×0.035 = 0.9975；fv = 997500
        assert resp.fair_value == "997500.00"
        assert "Level 2" in resp.valuation_method
        assert "3 期" in resp.valuation_method
        assert resp.dcf_details is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. LEVEL 3 — DCF 折现模型（不可观察输入）
# ═══════════════════════════════════════════════════════════════════════════════


class TestLevel3Dcf:
    """Level 3: NPV = Σ(CF_i / (1+r)^i) + terminal_value/(1+r)^n"""

    def test_single_period_no_terminal(self):
        """单期 CF=100000, r=0.10 → NPV = 100000/1.10 = 90909.09"""
        npv, details = _calc_level_3_fv(
            cash_flows=[Decimal("100000")],
            discount_rate=Decimal("0.10"),
            terminal_value=Decimal("0"),
        )
        expected = _quantize(Decimal("100000") / Decimal("1.10"))
        assert npv == expected
        assert len(details) == 1
        assert details[0]["period"] == 1

    def test_five_period_with_terminal(self):
        """5 期 CF=200000 r=0.10 + terminal=500000 → NPV ≈ 1068592"""
        npv, details = _calc_level_3_fv(
            cash_flows=[Decimal("200000")] * 5,
            discount_rate=Decimal("0.10"),
            terminal_value=Decimal("500000"),
        )
        # CF PV ≈ 758157.35
        # Terminal PV = 500000 / 1.61051 ≈ 310460.66
        # Total ≈ 1068618
        assert len(details) == 6  # 5 periods + terminal
        assert npv > Decimal("1060000")
        assert npv < Decimal("1075000")
        # terminal entry has period label
        assert "终值" in str(details[-1]["period"])

    def test_zero_cash_flows_only_terminal(self):
        """全零现金流仅终值 → NPV = terminal/(1+r)^n"""
        npv, _ = _calc_level_3_fv(
            cash_flows=[Decimal("0"), Decimal("0"), Decimal("0")],
            discount_rate=Decimal("0.10"),
            terminal_value=Decimal("100000"),
        )
        # 100000 / 1.331 ≈ 75131.48
        assert npv > Decimal("75000")
        assert npv < Decimal("76000")

    def test_high_discount_rate_drops_npv(self):
        """折现率=0.50 大幅降低现值"""
        npv, _ = _calc_level_3_fv(
            cash_flows=[Decimal("100000")] * 3,
            discount_rate=Decimal("0.50"),
            terminal_value=Decimal("0"),
        )
        assert npv > Decimal("130000")
        assert npv < Decimal("150000")

    def test_endpoint_response_for_level_3(self):
        """Level 3 endpoint 返回 dcf_details + valuation_method 含折现率"""

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = FairValueTestRequest(
                level=3,
                instrument_type="其他权益工具投资",
                face_value=Decimal("1000000"),
                cash_flow_projections=[Decimal("200000")] * 5,
                discount_rate=Decimal("0.10"),
                terminal_value=Decimal("500000"),
            )
            return await g_fair_value_test(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.level == 3
        assert resp.dcf_details is not None
        assert len(resp.dcf_details) == 6  # 5 periods + terminal
        assert "Level 3（DCF" in resp.valuation_method
        assert "discount_rate=0.10" in resp.valuation_method


# ═══════════════════════════════════════════════════════════════════════════════
# 4. VALIDATION — 必填字段 / 越界
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidationLevel1:
    """Level 1 校验：market_price + price_date 必填，市场报价 ≥ 0"""

    def test_missing_market_price_returns_422(self):
        payload = FairValueTestRequest(
            level=1,
            instrument_type="股票",
            face_value=Decimal("1000"),
            market_price=None,
            price_date="2026-05-19",
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 422
        assert "market_price" in exc_info.value.detail

    def test_missing_price_date_returns_422(self):
        payload = FairValueTestRequest(
            level=1,
            instrument_type="股票",
            face_value=Decimal("1000"),
            market_price=Decimal("10.0"),
            price_date=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 422
        assert "price_date" in exc_info.value.detail


class TestValidationLevel2:
    """Level 2 校验：interest_rate_curve / credit_spread / volatility 必填，rate ∈ [0,1)"""

    def test_missing_interest_rate_curve_returns_422(self):
        payload = FairValueTestRequest(
            level=2,
            instrument_type="债权投资",
            face_value=Decimal("1000"),
            interest_rate_curve=None,
            credit_spread=Decimal("0.02"),
            volatility=Decimal("0.1"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 422
        assert "interest_rate_curve" in exc_info.value.detail

    def test_empty_interest_rate_curve_returns_422(self):
        payload = FairValueTestRequest(
            level=2,
            instrument_type="债权投资",
            face_value=Decimal("1000"),
            interest_rate_curve=[],
            credit_spread=Decimal("0.02"),
            volatility=Decimal("0.1"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 422

    def test_missing_credit_spread_returns_422(self):
        payload = FairValueTestRequest(
            level=2,
            instrument_type="债权投资",
            face_value=Decimal("1000"),
            interest_rate_curve=[Decimal("0.03")],
            credit_spread=None,
            volatility=Decimal("0.1"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 422

    def test_missing_volatility_returns_422(self):
        payload = FairValueTestRequest(
            level=2,
            instrument_type="债权投资",
            face_value=Decimal("1000"),
            interest_rate_curve=[Decimal("0.03")],
            credit_spread=Decimal("0.02"),
            volatility=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 422


class TestValidationLevel3:
    """Level 3 校验：cash_flow_projections / discount_rate 必填，rate ∈ (0, 1)"""

    def test_missing_cash_flows_returns_422(self):
        payload = FairValueTestRequest(
            level=3,
            instrument_type="其他权益工具投资",
            face_value=Decimal("1000"),
            cash_flow_projections=None,
            discount_rate=Decimal("0.10"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 422

    def test_empty_cash_flows_returns_422(self):
        payload = FairValueTestRequest(
            level=3,
            instrument_type="其他权益工具投资",
            face_value=Decimal("1000"),
            cash_flow_projections=[],
            discount_rate=Decimal("0.10"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 422

    def test_missing_discount_rate_returns_422(self):
        payload = FairValueTestRequest(
            level=3,
            instrument_type="其他权益工具投资",
            face_value=Decimal("1000"),
            cash_flow_projections=[Decimal("100000")],
            discount_rate=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 422

    def test_discount_rate_zero_returns_400(self):
        """discount_rate = 0 → 400（超出 0~1 开区间）"""
        payload = FairValueTestRequest(
            level=3,
            instrument_type="其他权益工具投资",
            face_value=Decimal("1000"),
            cash_flow_projections=[Decimal("100000")],
            discount_rate=Decimal("0"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400
        assert "折现率" in exc_info.value.detail

    def test_discount_rate_one_returns_400(self):
        """discount_rate = 1 → 400（超出 0~1 开区间）"""
        payload = FairValueTestRequest(
            level=3,
            instrument_type="其他权益工具投资",
            face_value=Decimal("1000"),
            cash_flow_projections=[Decimal("100000")],
            discount_rate=Decimal("1.0"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400


class TestValidationCommon:
    """跨 level 的通用校验"""

    def test_face_value_must_be_positive_pydantic_level(self):
        """face_value ≤ 0 在 pydantic schema 层就会被拦截（gt=0）"""
        with pytest.raises(Exception):
            FairValueTestRequest(
                level=1,
                instrument_type="股票",
                face_value=Decimal("0"),
                market_price=Decimal("10"),
                price_date="2026-05-19",
            )

    def test_face_value_above_1e15_returns_400(self):
        """面值 > 1e15 → 400（超出合理范围）"""
        payload = FairValueTestRequest(
            level=1,
            instrument_type="股票",
            face_value=Decimal("2e15"),
            market_price=Decimal("10"),
            price_date="2026-05-19",
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400
        assert "1e15" in exc_info.value.detail


class TestEndpointInvalidProjectId:
    """endpoint 入口检测 invalid project_id（非 UUID 格式）"""

    def test_invalid_project_id_returns_400(self):
        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = FairValueTestRequest(
                level=1,
                instrument_type="股票",
                face_value=Decimal("1000"),
                market_price=Decimal("10"),
                price_date="2026-05-19",
            )
            return await g_fair_value_test(
                project_id="not-a-valid-uuid",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(_run())
        assert exc_info.value.status_code == 400
        assert "invalid project_id" in exc_info.value.detail


# ═══════════════════════════════════════════════════════════════════════════════
# 5. WRITE-BACK — apply_to_sheet 写回 parsed_data.fair_value_tests[sheet]
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """写回 helper 函数签名 + 行为验证"""

    def test_writeback_helper_exists_and_callable(self):
        assert callable(_maybe_apply_fair_value_to_workpaper)

    def test_writeback_helper_is_async(self):
        assert inspect.iscoroutinefunction(_maybe_apply_fair_value_to_workpaper)

    def test_writeback_returns_none_when_apply_to_sheet_none(self):
        """apply_to_sheet=None → 直接返回 None（不访问 DB）"""

        async def _run():
            payload = FairValueTestRequest(
                level=1,
                instrument_type="股票",
                face_value=Decimal("1000"),
                market_price=Decimal("10"),
                price_date="2026-05-19",
                apply_to_sheet=None,
            )
            return await _maybe_apply_fair_value_to_workpaper(
                db=None,  # type: ignore[arg-type]
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                fair_value=Decimal("10000.00"),
                valuation_method="Level 1",
                conclusion="ok",
                dcf_details=None,
                is_llm_stub=False,
            )

        assert asyncio.run(_run()) is None

    def test_writeback_returns_none_when_invalid_wp_id(self):
        """apply_to_sheet 给定但 wp_id 非 UUID → 返回 None（防御性退出）"""

        async def _run():
            payload = FairValueTestRequest(
                level=1,
                instrument_type="股票",
                face_value=Decimal("1000"),
                market_price=Decimal("10"),
                price_date="2026-05-19",
                apply_to_sheet="G1-6 公允价值测试",
            )
            return await _maybe_apply_fair_value_to_workpaper(
                db=None,  # type: ignore[arg-type]
                wp_id="not-a-uuid",
                payload=payload,
                fair_value=Decimal("10000.00"),
                valuation_method="Level 1",
                conclusion="ok",
                dcf_details=None,
                is_llm_stub=False,
            )

        assert asyncio.run(_run()) is None

    def test_writeback_populates_parsed_data_structure(self):
        """apply_to_sheet 给定 + 找到 wp → parsed_data.fair_value_tests[sheet] 被填充"""
        wp = _FakeWorkpaper(parsed_data=None)
        mock_db = _FakeAsyncSession(workpaper=wp)
        sheet_name = "G1-6 公允价值测试"

        async def _run():
            payload = FairValueTestRequest(
                level=2,
                instrument_type="债权投资",
                face_value=Decimal("1000000"),
                interest_rate_curve=[Decimal("0.03"), Decimal("0.035")],
                credit_spread=Decimal("0.02"),
                volatility=Decimal("0.1"),
                apply_to_sheet=sheet_name,
            )
            return await _maybe_apply_fair_value_to_workpaper(
                db=mock_db,
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                fair_value=Decimal("980000.00"),
                valuation_method="Level 2 mock",
                conclusion="估值合理",
                dcf_details=None,
                is_llm_stub=False,
            )

        applied = asyncio.run(_run())
        assert applied == sheet_name
        assert wp.parsed_data is not None
        assert "fair_value_tests" in wp.parsed_data
        record = wp.parsed_data["fair_value_tests"][sheet_name]
        assert record["level"] == 2
        assert record["fair_value"] == "980000.00"
        assert record["instrument_type"] == "债权投资"
        assert record["valuation_method"] == "Level 2 mock"
        assert record["conclusion"] == "估值合理"
        assert record["is_llm_stub"] is False
        assert "applied_at" in record
        # Level 2 inputs回显
        assert record["inputs"]["credit_spread"] == "0.02"
        assert record["inputs"]["volatility"] == "0.1"
        assert record["inputs"]["interest_rate_curve"] == ["0.03", "0.035"]
        # DB 操作被调用
        assert mock_db.flush_called
        assert mock_db.commit_called

    def test_writeback_level_3_includes_dcf_details(self):
        """Level 3 写回时 dcf_details 也写入 parsed_data"""
        wp = _FakeWorkpaper(parsed_data={"existing": "data"})
        mock_db = _FakeAsyncSession(workpaper=wp)
        sheet_name = "G6 公允价值测试"

        async def _run():
            payload = FairValueTestRequest(
                level=3,
                instrument_type="其他权益工具投资",
                face_value=Decimal("1000000"),
                cash_flow_projections=[Decimal("100000"), Decimal("100000")],
                discount_rate=Decimal("0.10"),
                terminal_value=Decimal("500000"),
                apply_to_sheet=sheet_name,
            )
            return await _maybe_apply_fair_value_to_workpaper(
                db=mock_db,
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                fair_value=Decimal("586776.86"),
                valuation_method="Level 3 DCF",
                conclusion="估值偏离 ...",
                dcf_details=[{"period": 1, "cash_flow": "100000", "discount_factor": "1.10", "present_value": "90909.09"}],
                is_llm_stub=True,
            )

        applied = asyncio.run(_run())
        assert applied == sheet_name
        # 既有数据保留
        assert wp.parsed_data["existing"] == "data"
        record = wp.parsed_data["fair_value_tests"][sheet_name]
        assert record["level"] == 3
        assert record["is_llm_stub"] is True
        assert record["dcf_details"] is not None
        assert len(record["dcf_details"]) == 1
        # Level 3 inputs回显
        assert record["inputs"]["discount_rate"] == "0.10"
        assert record["inputs"]["terminal_value"] == "500000"
        assert record["inputs"]["cash_flow_projections"] == ["100000", "100000"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. RBAC — require_project_access("edit") 强制校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC enforcement tests"""

    def test_route_uses_require_project_access_edit(self):
        """G-F4 路由必须用 require_project_access('edit')，不能裸用 get_current_user"""
        import app.routers.wp_g_fair_value as mod
        src = inspect.getsource(mod)
        assert 'require_project_access("edit")' in src, \
            "wp_g_fair_value 必须用 require_project_access('edit')"

    def test_endpoint_function_has_user_dependency(self):
        """endpoint 函数签名包含 _user 参数（RBAC 注入）"""
        sig = inspect.signature(g_fair_value_test)
        assert "_user" in sig.parameters

    def test_router_prefix_contains_project_id(self):
        """路由前缀含 {project_id} 提供 RBAC 上下文"""
        assert "{project_id}" in router.prefix
        assert "/g" in router.prefix

    def test_endpoint_is_async(self):
        assert inspect.iscoroutinefunction(g_fair_value_test)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. is_llm_stub — 由 settings.WP_AI_SERVICE_ENABLED 驱动（不能硬编码）
# ═══════════════════════════════════════════════════════════════════════════════


class TestStubFlagDrivenBySettings:
    """is_llm_stub 字段必须由 settings.WP_AI_SERVICE_ENABLED 驱动（参考 RE-I1 模式）"""

    def test_is_llm_stub_true_when_ai_disabled_level_3(self, monkeypatch):
        """settings.WP_AI_SERVICE_ENABLED=False → is_llm_stub=True + Level 3 conclusion 含 stub 提示"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", False)

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = FairValueTestRequest(
                level=3,
                instrument_type="其他权益工具投资",
                face_value=Decimal("1000000"),
                cash_flow_projections=[Decimal("100000")] * 5,
                discount_rate=Decimal("0.10"),
                terminal_value=Decimal("500000"),
            )
            return await g_fair_value_test(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.is_llm_stub is True
        assert "wp_ai_service" in resp.conclusion

    def test_is_llm_stub_false_when_ai_enabled_level_3(self, monkeypatch):
        """settings.WP_AI_SERVICE_ENABLED=True → is_llm_stub=False + Level 3 conclusion 无 stub 提示"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", True)

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = FairValueTestRequest(
                level=3,
                instrument_type="其他权益工具投资",
                face_value=Decimal("1000000"),
                cash_flow_projections=[Decimal("100000")] * 5,
                discount_rate=Decimal("0.10"),
                terminal_value=Decimal("500000"),
            )
            return await g_fair_value_test(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.is_llm_stub is False
        assert "wp_ai_service" not in resp.conclusion

    def test_is_llm_stub_reflected_in_level_1_response(self, monkeypatch):
        """Level 1 也返回 is_llm_stub 字段（统一接口契约），但 conclusion 不附 stub 提示"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", False)

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = FairValueTestRequest(
                level=1,
                instrument_type="股票",
                face_value=Decimal("1000"),
                market_price=Decimal("10"),
                price_date="2026-05-19",
            )
            return await g_fair_value_test(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        # is_llm_stub 仍然反映 settings 状态
        assert resp.is_llm_stub is True
        # 但 Level 1 conclusion 不附加 stub 提示（仅 Level 3 才附加）
        assert "wp_ai_service" not in resp.conclusion


# ═══════════════════════════════════════════════════════════════════════════════
# 8. _quantize 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


class TestQuantize:
    """_quantize 保留 2 位小数 HALF_UP"""

    def test_rounds_half_up(self):
        assert _quantize(Decimal("1.005")) == Decimal("1.01")
        assert _quantize(Decimal("1.004")) == Decimal("1.00")

    def test_preserves_exact_values(self):
        assert _quantize(Decimal("100.00")) == Decimal("100.00")
        assert _quantize(Decimal("0.01")) == Decimal("0.01")


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — fake DB / fake workpaper for write-back testing without real engine
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeWorkpaper:
    """Mimics WorkingPaper ORM instance（仅 parsed_data 字段）"""

    def __init__(self, parsed_data: dict | None = None):
        self.parsed_data = parsed_data


class _FakeScalarResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeAsyncSession:
    """Async session stub: execute() returns the configured workpaper; tracks flush/commit"""

    def __init__(self, workpaper=None):
        self._workpaper = workpaper
        self.flush_called = False
        self.commit_called = False

    async def execute(self, _stmt):
        return _FakeScalarResult(self._workpaper)

    async def flush(self):
        self.flush_called = True

    async def commit(self):
        self.commit_called = True


def _make_mock_db_no_writeback():
    """对于 apply_to_sheet=None 路径的测试，DB 永远不会被真正使用，但 endpoint 形参需要 AsyncSession 类型对象"""
    return _FakeAsyncSession(workpaper=None)
