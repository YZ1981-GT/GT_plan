"""Unit tests for G-F5 ECL 三阶段模型 (IFRS 9 / CAS 22 预期信用损失)
— formula correctness × 3 stages × 3 boundary cases + monotonicity + write-back + RBAC + is_llm_stub.

Covers:
- Stage 1: ECL = book_value × pd_12m × lgd（12 个月预期信用损失，信用风险未显著增加）
- Stage 2: ECL = book_value × pd_lifetime × lgd（整个存续期，未信用减值）
- Stage 3: ECL = book_value × pd_lifetime × lgd（已信用减值，PD 接近 100%）
- Monotonicity: ECL(1) ≤ ECL(2) ≤ ECL(3) when pd_12m ≤ pd_lifetime
- Validation: book_value=0 → 400 / lgd>1 → 400 / pd_12m>pd_lifetime → 400 / pd ∉ [0,1] → 400
- Write-back: parsed_data.ecl_calcs[sheet] data structure + apply_to_sheet=None returns None
- RBAC: require_project_access("edit") enforced + endpoint has _user param
- is_llm_stub: always False (deterministic formula, no LLM involvement)

对应 spec: workpaper-g-investment-cycle G-F5 / ADR-G4 / CP-6
对应 task: Sprint 2 Task 2.10
"""

from __future__ import annotations

import sys

sys.path.insert(0, "backend")

import asyncio
import inspect
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.routers.wp_g_ecl import (
    ECLCalcRequest,
    ECLCalcResponse,
    _calc_ecl_stage_1,
    _calc_ecl_stage_2,
    _calc_ecl_stage_3,
    _check_monotonicity,
    _maybe_apply_ecl_to_workpaper,
    _quantize,
    _validate_inputs,
    g_ecl_calc,
    router,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. STAGE 1 — 12 个月 ECL（信用风险未显著增加）
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage1Ecl:
    """Stage 1: ECL = book_value × pd_12m × lgd，3 boundary cases"""

    def test_stage1_small_pd_low_loss(self):
        """边界 case 1: 小 PD（0.01）+ 中等 LGD → 较低 ECL"""
        ecl = _calc_ecl_stage_1(
            book_value=Decimal("1000000"),
            pd_12m=Decimal("0.01"),
            lgd=Decimal("0.45"),
        )
        # 1000000 × 0.01 × 0.45 = 4500.00
        assert ecl == Decimal("4500.00")

    def test_stage1_large_pd_significant_loss(self):
        """边界 case 2: 大 PD（0.30）+ 高 LGD → 显著 ECL"""
        ecl = _calc_ecl_stage_1(
            book_value=Decimal("1000000"),
            pd_12m=Decimal("0.30"),
            lgd=Decimal("0.80"),
        )
        # 1000000 × 0.30 × 0.80 = 240000.00
        assert ecl == Decimal("240000.00")

    def test_stage1_zero_pd_returns_zero(self):
        """边界 case 3: PD=0 → ECL=0（PD 边界值）"""
        ecl = _calc_ecl_stage_1(
            book_value=Decimal("1000000"),
            pd_12m=Decimal("0"),
            lgd=Decimal("0.50"),
        )
        assert ecl == Decimal("0.00")

    def test_stage1_endpoint_response(self):
        """Stage 1 endpoint 返回完整字段 + formula_used 含 PD_12m"""

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ECLCalcRequest(
                stage=1,
                book_value=Decimal("1000000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.20"),
                lgd=Decimal("0.40"),
            )
            return await g_ecl_calc(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert isinstance(resp, ECLCalcResponse)
        assert resp.stage == 1
        # 1000000 × 0.05 × 0.40 = 20000.00
        assert resp.ecl_amount == "20000.00"
        assert "Stage 1" in resp.formula_used
        assert "PD_12m" in resp.formula_used
        assert resp.monotonicity_check is True
        assert resp.is_llm_stub is False
        assert resp.applied_to_sheet is None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. STAGE 2 — 存续期 ECL（信用风险显著增加，未信用减值）
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage2Ecl:
    """Stage 2: ECL = book_value × pd_lifetime × lgd，3 boundary cases"""

    def test_stage2_small_pd_lifetime(self):
        """边界 case 1: 小 PD_lifetime（0.05）→ 较低 ECL"""
        ecl = _calc_ecl_stage_2(
            book_value=Decimal("1000000"),
            pd_lifetime=Decimal("0.05"),
            lgd=Decimal("0.45"),
        )
        # 1000000 × 0.05 × 0.45 = 22500.00
        assert ecl == Decimal("22500.00")

    def test_stage2_large_pd_lifetime(self):
        """边界 case 2: 大 PD_lifetime（0.50）+ 高 LGD → 显著 ECL"""
        ecl = _calc_ecl_stage_2(
            book_value=Decimal("1000000"),
            pd_lifetime=Decimal("0.50"),
            lgd=Decimal("0.80"),
        )
        # 1000000 × 0.50 × 0.80 = 400000.00
        assert ecl == Decimal("400000.00")

    def test_stage2_zero_lgd_returns_zero(self):
        """边界 case 3: LGD=0 → ECL=0（违约时无损失，纯担保）"""
        ecl = _calc_ecl_stage_2(
            book_value=Decimal("1000000"),
            pd_lifetime=Decimal("0.30"),
            lgd=Decimal("0"),
        )
        assert ecl == Decimal("0.00")

    def test_stage2_endpoint_response(self):
        """Stage 2 endpoint 返回 formula_used 含 PD_lifetime"""

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ECLCalcRequest(
                stage=2,
                book_value=Decimal("500000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.25"),
                lgd=Decimal("0.50"),
            )
            return await g_ecl_calc(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.stage == 2
        # 500000 × 0.25 × 0.50 = 62500.00
        assert resp.ecl_amount == "62500.00"
        assert "Stage 2" in resp.formula_used
        assert "PD_lifetime" in resp.formula_used
        assert resp.monotonicity_check is True
        assert resp.is_llm_stub is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. STAGE 3 — 存续期 ECL（已信用减值，PD 接近 100%）
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage3Ecl:
    """Stage 3: ECL = book_value × pd_lifetime × lgd，3 boundary cases（PD 接近 100%）"""

    def test_stage3_pd_90_percent(self):
        """边界 case 1: PD_lifetime=0.90（已信用减值的最低边界）"""
        ecl = _calc_ecl_stage_3(
            book_value=Decimal("1000000"),
            pd_lifetime=Decimal("0.90"),
            lgd=Decimal("0.60"),
        )
        # 1000000 × 0.90 × 0.60 = 540000.00
        assert ecl == Decimal("540000.00")

    def test_stage3_pd_95_percent(self):
        """边界 case 2: PD_lifetime=0.95（典型已信用减值水平）"""
        ecl = _calc_ecl_stage_3(
            book_value=Decimal("1000000"),
            pd_lifetime=Decimal("0.95"),
            lgd=Decimal("0.70"),
        )
        # 1000000 × 0.95 × 0.70 = 665000.00
        assert ecl == Decimal("665000.00")

    def test_stage3_pd_100_percent(self):
        """边界 case 3: PD_lifetime=1.00（违约确定 → ECL = book_value × LGD）"""
        ecl = _calc_ecl_stage_3(
            book_value=Decimal("1000000"),
            pd_lifetime=Decimal("1.0"),
            lgd=Decimal("0.50"),
        )
        # 1000000 × 1.0 × 0.50 = 500000.00（PD=100% 时 ECL = book_value × LGD）
        assert ecl == Decimal("500000.00")

    def test_stage3_endpoint_response(self):
        """Stage 3 endpoint 返回 formula_used 含 '已发生信用减值'"""

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ECLCalcRequest(
                stage=3,
                book_value=Decimal("800000"),
                pd_12m=Decimal("0.10"),
                pd_lifetime=Decimal("0.95"),
                lgd=Decimal("0.65"),
            )
            return await g_ecl_calc(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.stage == 3
        # 800000 × 0.95 × 0.65 = 494000.00
        assert resp.ecl_amount == "494000.00"
        assert "Stage 3" in resp.formula_used
        assert "已发生信用减值" in resp.formula_used or "PD 接近 100%" in resp.formula_used
        assert resp.monotonicity_check is True
        assert resp.is_llm_stub is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. MONOTONICITY — Stage 1 ≤ Stage 2 ≤ Stage 3（CP-6）
# ═══════════════════════════════════════════════════════════════════════════════


class TestMonotonicity:
    """单调性约束：当 pd_12m ≤ pd_lifetime 时，ECL(1) ≤ ECL(2) ≤ ECL(3)"""

    def test_monotonicity_holds_typical_inputs(self):
        """典型输入：pd_12m=0.02 < pd_lifetime=0.20 → 单调性成立"""
        ok = _check_monotonicity(
            book_value=Decimal("1000000"),
            pd_12m=Decimal("0.02"),
            pd_lifetime=Decimal("0.20"),
            lgd=Decimal("0.50"),
        )
        assert ok is True

    def test_monotonicity_holds_when_pd_equal(self):
        """边界：pd_12m = pd_lifetime → ECL(1) = ECL(2) = ECL(3)，单调性 (≤) 成立"""
        ok = _check_monotonicity(
            book_value=Decimal("500000"),
            pd_12m=Decimal("0.10"),
            pd_lifetime=Decimal("0.10"),
            lgd=Decimal("0.40"),
        )
        assert ok is True

    def test_monotonicity_holds_with_extreme_book_value(self):
        """大额 book_value：1e10 × 各阶段 PD → 单调性仍成立"""
        ok = _check_monotonicity(
            book_value=Decimal("10000000000"),
            pd_12m=Decimal("0.05"),
            pd_lifetime=Decimal("0.50"),
            lgd=Decimal("0.80"),
        )
        assert ok is True

    def test_endpoint_explicit_monotonicity_check_field(self):
        """endpoint 响应必须包含 monotonicity_check=True 字段（合法输入下恒为 True）"""

        async def _run(stage):
            mock_db = _make_mock_db_no_writeback()
            payload = ECLCalcRequest(
                stage=stage,
                book_value=Decimal("1000000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.30"),
                lgd=Decimal("0.50"),
            )
            return await g_ecl_calc(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        for stg in (1, 2, 3):
            resp = asyncio.run(_run(stg))
            assert resp.monotonicity_check is True, f"Stage {stg} 单调性必须为 True"

    def test_cross_stage_amounts_obey_ordering(self):
        """显式调用 3 stage endpoint 验证返回 ECL(1) ≤ ECL(2) ≤ ECL(3)"""

        async def _run(stage):
            mock_db = _make_mock_db_no_writeback()
            payload = ECLCalcRequest(
                stage=stage,
                book_value=Decimal("1000000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.30"),
                lgd=Decimal("0.50"),
            )
            return await g_ecl_calc(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        e1 = Decimal(asyncio.run(_run(1)).ecl_amount)
        e2 = Decimal(asyncio.run(_run(2)).ecl_amount)
        e3 = Decimal(asyncio.run(_run(3)).ecl_amount)
        # pd_12m=0.05 < pd_lifetime=0.30 → e1 < e2 = e3（公式上 Stage 2/3 公式相同）
        assert e1 <= e2
        assert e2 <= e3


# ═══════════════════════════════════════════════════════════════════════════════
# 5. VALIDATION — book_value/lgd/pd 边界 + pd_12m vs pd_lifetime
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidationBookValue:
    """book_value 校验：=0 / <0 / >1e15 → 400"""

    def test_book_value_zero_returns_400(self):
        payload = ECLCalcRequest(
            stage=1,
            book_value=Decimal("0"),
            pd_12m=Decimal("0.05"),
            pd_lifetime=Decimal("0.20"),
            lgd=Decimal("0.50"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400
        assert "账面余额" in exc_info.value.detail

    def test_book_value_negative_returns_400(self):
        payload = ECLCalcRequest(
            stage=1,
            book_value=Decimal("-1000"),
            pd_12m=Decimal("0.05"),
            pd_lifetime=Decimal("0.20"),
            lgd=Decimal("0.50"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400
        assert "账面余额" in exc_info.value.detail

    def test_book_value_above_1e15_returns_400(self):
        payload = ECLCalcRequest(
            stage=1,
            book_value=Decimal("2e15"),
            pd_12m=Decimal("0.05"),
            pd_lifetime=Decimal("0.20"),
            lgd=Decimal("0.50"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400
        assert "1e15" in exc_info.value.detail


class TestValidationLgd:
    """LGD 校验：>1 / <0 → 400"""

    def test_lgd_above_one_returns_400(self):
        payload = ECLCalcRequest(
            stage=1,
            book_value=Decimal("1000"),
            pd_12m=Decimal("0.05"),
            pd_lifetime=Decimal("0.20"),
            lgd=Decimal("1.5"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400
        assert "LGD" in exc_info.value.detail

    def test_lgd_negative_returns_400(self):
        payload = ECLCalcRequest(
            stage=1,
            book_value=Decimal("1000"),
            pd_12m=Decimal("0.05"),
            pd_lifetime=Decimal("0.20"),
            lgd=Decimal("-0.1"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400
        assert "LGD" in exc_info.value.detail


class TestValidationPd:
    """PD 校验：pd_12m / pd_lifetime ∉ [0,1] → 400"""

    def test_pd_12m_above_one_returns_400(self):
        payload = ECLCalcRequest(
            stage=1,
            book_value=Decimal("1000"),
            pd_12m=Decimal("1.5"),
            pd_lifetime=Decimal("1.5"),
            lgd=Decimal("0.50"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400
        assert "PD" in exc_info.value.detail

    def test_pd_12m_negative_returns_400(self):
        payload = ECLCalcRequest(
            stage=1,
            book_value=Decimal("1000"),
            pd_12m=Decimal("-0.1"),
            pd_lifetime=Decimal("0.20"),
            lgd=Decimal("0.50"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400

    def test_pd_lifetime_above_one_returns_400(self):
        payload = ECLCalcRequest(
            stage=2,
            book_value=Decimal("1000"),
            pd_12m=Decimal("0.05"),
            pd_lifetime=Decimal("1.5"),
            lgd=Decimal("0.50"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400
        assert "PD" in exc_info.value.detail

    def test_pd_lifetime_negative_returns_400(self):
        payload = ECLCalcRequest(
            stage=2,
            book_value=Decimal("1000"),
            pd_12m=Decimal("0"),
            pd_lifetime=Decimal("-0.1"),
            lgd=Decimal("0.50"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400


class TestValidationMonotonicityPrecondition:
    """单调性前提条件：pd_12m > pd_lifetime → 400（违反业务约束）"""

    def test_pd_12m_exceeds_pd_lifetime_returns_400(self):
        payload = ECLCalcRequest(
            stage=1,
            book_value=Decimal("1000"),
            pd_12m=Decimal("0.50"),
            pd_lifetime=Decimal("0.30"),
            lgd=Decimal("0.50"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_inputs(payload)
        assert exc_info.value.status_code == 400
        assert "12 个月 PD 不应大于存续期 PD" in exc_info.value.detail

    def test_pd_12m_equals_pd_lifetime_passes(self):
        """边界：pd_12m = pd_lifetime → 不抛异常（≤ 关系）"""
        payload = ECLCalcRequest(
            stage=2,
            book_value=Decimal("1000"),
            pd_12m=Decimal("0.10"),
            pd_lifetime=Decimal("0.10"),
            lgd=Decimal("0.50"),
        )
        # 不应抛异常
        _validate_inputs(payload)


class TestEndpointInvalidProjectId:
    """endpoint 入口检测 invalid project_id（非 UUID 格式）"""

    def test_invalid_project_id_returns_400(self):
        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ECLCalcRequest(
                stage=1,
                book_value=Decimal("1000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.20"),
                lgd=Decimal("0.50"),
            )
            return await g_ecl_calc(
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
# 6. WRITE-BACK — apply_to_sheet 写回 parsed_data.ecl_calcs[sheet]
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """写回 helper 函数签名 + 行为验证（与 wp_g_fair_value.fair_value_tests 对称）"""

    def test_writeback_helper_exists_and_callable(self):
        assert callable(_maybe_apply_ecl_to_workpaper)

    def test_writeback_helper_is_async(self):
        assert inspect.iscoroutinefunction(_maybe_apply_ecl_to_workpaper)

    def test_writeback_returns_none_when_apply_to_sheet_none(self):
        """apply_to_sheet=None → 直接返回 None（不访问 DB）"""

        async def _run():
            payload = ECLCalcRequest(
                stage=1,
                book_value=Decimal("1000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.20"),
                lgd=Decimal("0.50"),
                apply_to_sheet=None,
            )
            return await _maybe_apply_ecl_to_workpaper(
                db=None,  # type: ignore[arg-type]
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                ecl_amount=Decimal("10.00"),
                formula_used="Stage 1",
                monotonicity_check=True,
            )

        assert asyncio.run(_run()) is None

    def test_writeback_returns_none_when_invalid_wp_id(self):
        """apply_to_sheet 给定但 wp_id 非 UUID → 返回 None（防御性退出）"""

        async def _run():
            payload = ECLCalcRequest(
                stage=1,
                book_value=Decimal("1000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.20"),
                lgd=Decimal("0.50"),
                apply_to_sheet="ECL测试表G4",
            )
            return await _maybe_apply_ecl_to_workpaper(
                db=None,  # type: ignore[arg-type]
                wp_id="not-a-uuid",
                payload=payload,
                ecl_amount=Decimal("10.00"),
                formula_used="Stage 1",
                monotonicity_check=True,
            )

        assert asyncio.run(_run()) is None

    def test_writeback_populates_parsed_data_structure(self):
        """apply_to_sheet 给定 + 找到 wp → parsed_data.ecl_calcs[sheet] 被填充"""
        wp = _FakeWorkpaper(parsed_data=None)
        mock_db = _FakeAsyncSession(workpaper=wp)
        sheet_name = "ECL测试表G4-7"

        async def _run():
            payload = ECLCalcRequest(
                stage=2,
                book_value=Decimal("1000000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.30"),
                lgd=Decimal("0.50"),
                apply_to_sheet=sheet_name,
            )
            return await _maybe_apply_ecl_to_workpaper(
                db=mock_db,
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                ecl_amount=Decimal("150000.00"),
                formula_used="Stage 2 公式",
                monotonicity_check=True,
            )

        applied = asyncio.run(_run())
        assert applied == sheet_name
        assert wp.parsed_data is not None
        assert "ecl_calcs" in wp.parsed_data
        record = wp.parsed_data["ecl_calcs"][sheet_name]
        assert record["stage"] == 2
        assert record["ecl_amount"] == "150000.00"
        assert record["formula_used"] == "Stage 2 公式"
        assert record["monotonicity_check"] is True
        assert "applied_at" in record
        # inputs 回显
        assert record["inputs"]["book_value"] == "1000000"
        assert record["inputs"]["pd_12m"] == "0.05"
        assert record["inputs"]["pd_lifetime"] == "0.30"
        assert record["inputs"]["lgd"] == "0.50"
        # DB 操作被调用
        assert mock_db.flush_called
        assert mock_db.commit_called

    def test_writeback_preserves_existing_parsed_data(self):
        """已有 parsed_data 时新增 ecl_calcs 不破坏原有数据"""
        wp = _FakeWorkpaper(parsed_data={"existing": "data", "fair_value_tests": {"sheet_x": "..."}})
        mock_db = _FakeAsyncSession(workpaper=wp)
        sheet_name = "ECL测试表G6-5"

        async def _run():
            payload = ECLCalcRequest(
                stage=3,
                book_value=Decimal("500000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.95"),
                lgd=Decimal("0.70"),
                apply_to_sheet=sheet_name,
            )
            return await _maybe_apply_ecl_to_workpaper(
                db=mock_db,
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                ecl_amount=Decimal("332500.00"),
                formula_used="Stage 3 公式",
                monotonicity_check=True,
            )

        asyncio.run(_run())
        # 既有数据保留
        assert wp.parsed_data["existing"] == "data"
        assert wp.parsed_data["fair_value_tests"]["sheet_x"] == "..."
        # 新增数据
        assert wp.parsed_data["ecl_calcs"][sheet_name]["stage"] == 3

    def test_writeback_endpoint_e2e(self):
        """endpoint 端到端：apply_to_sheet 给定 → response.applied_to_sheet 同步返回"""
        wp = _FakeWorkpaper(parsed_data=None)
        mock_db = _FakeAsyncSession(workpaper=wp)
        sheet_name = "明细表G4-2"

        async def _run():
            payload = ECLCalcRequest(
                stage=1,
                book_value=Decimal("2000000"),
                pd_12m=Decimal("0.03"),
                pd_lifetime=Decimal("0.15"),
                lgd=Decimal("0.40"),
                apply_to_sheet=sheet_name,
            )
            return await g_ecl_calc(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.applied_to_sheet == sheet_name
        assert resp.stage == 1
        # 2000000 × 0.03 × 0.40 = 24000.00
        assert resp.ecl_amount == "24000.00"
        # parsed_data 同步写入
        assert wp.parsed_data["ecl_calcs"][sheet_name]["ecl_amount"] == "24000.00"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. RBAC — require_project_access("edit") 强制校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC enforcement tests"""

    def test_route_uses_require_project_access_edit(self):
        """G-F5 路由必须用 require_project_access('edit')，不能裸用 get_current_user"""
        import app.routers.wp_g_ecl as mod
        src = inspect.getsource(mod)
        assert 'require_project_access("edit")' in src, \
            "wp_g_ecl 必须用 require_project_access('edit')"

    def test_endpoint_function_has_user_dependency(self):
        """endpoint 函数签名包含 _user 参数（RBAC 注入）"""
        sig = inspect.signature(g_ecl_calc)
        assert "_user" in sig.parameters

    def test_router_prefix_contains_project_id(self):
        """路由前缀含 {project_id} 提供 RBAC 上下文"""
        assert "{project_id}" in router.prefix
        assert "/g" in router.prefix

    def test_router_prefix_contains_wp_id(self):
        """路由前缀含 {wp_id} 提供 workpaper 上下文"""
        assert "{wp_id}" in router.prefix

    def test_endpoint_is_async(self):
        assert inspect.iscoroutinefunction(g_ecl_calc)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. is_llm_stub — 总是 False（确定性公式，不涉及 LLM）
# ═══════════════════════════════════════════════════════════════════════════════


class TestStubFlagAlwaysFalse:
    """is_llm_stub 字段对 ECL 三阶段模型必须始终为 False（确定性公式）"""

    def test_is_llm_stub_false_stage_1(self):
        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ECLCalcRequest(
                stage=1,
                book_value=Decimal("1000000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.20"),
                lgd=Decimal("0.50"),
            )
            return await g_ecl_calc(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.is_llm_stub is False

    def test_is_llm_stub_false_stage_2(self):
        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ECLCalcRequest(
                stage=2,
                book_value=Decimal("1000000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.30"),
                lgd=Decimal("0.50"),
            )
            return await g_ecl_calc(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.is_llm_stub is False

    def test_is_llm_stub_false_stage_3(self):
        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ECLCalcRequest(
                stage=3,
                book_value=Decimal("1000000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.95"),
                lgd=Decimal("0.70"),
            )
            return await g_ecl_calc(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        assert resp.is_llm_stub is False

    def test_is_llm_stub_independent_of_settings(self, monkeypatch):
        """ECL 是确定性公式，is_llm_stub 不应受 settings.WP_AI_SERVICE_ENABLED 影响"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", True, raising=False)

        async def _run():
            mock_db = _make_mock_db_no_writeback()
            payload = ECLCalcRequest(
                stage=2,
                book_value=Decimal("1000000"),
                pd_12m=Decimal("0.05"),
                pd_lifetime=Decimal("0.30"),
                lgd=Decimal("0.50"),
            )
            return await g_ecl_calc(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=payload,
                db=mock_db,
                _user=object(),
            )

        resp = asyncio.run(_run())
        # 即使 AI 启用，ECL 仍然是 deterministic 公式
        assert resp.is_llm_stub is False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. _quantize 辅助函数
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
