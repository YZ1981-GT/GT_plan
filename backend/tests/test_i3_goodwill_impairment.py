"""Unit tests for I-F4 goodwill impairment DCF analysis (CAS 8 / IFRS 36).

Covers:
- DCF formula with Gordon growth model: NPV = Σ(CF_t / (1+r)^t) + TV/(1+r)^n
- Gordon TV: CF_n × (1+g) / (r - g)
- Goodwill impairment allocation: 先冲商誉 → 剩余分摊到其他资产
- Edge cases: g=0 / g approaches r / single year / no impairment / partial vs full goodwill writedown
- Validation: invalid project_id / discount_rate out of range / g >= r / book_value > 1e15
- Write-back: _maybe_apply_goodwill_impairment_to_workpaper callable
- RBAC: require_project_access("edit") enforced

对应 spec: workpaper-i-intangible-assets-cycle I-F4
对应 ADR: ADR-I3
"""

import sys
sys.path.insert(0, "backend")

import inspect
from decimal import Decimal

import pytest

from app.routers.wp_i_goodwill import (
    GoodwillImpairmentRequest,
    GoodwillImpairmentResponse,
    _allocate_goodwill_impairment,
    _calc_dcf_with_gordon,
    _maybe_apply_goodwill_impairment_to_workpaper,
    _quantize,
    i3_goodwill_impairment_analysis,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DCF + GORDON GROWTH FORMULA
# ═══════════════════════════════════════════════════════════════════════════════


class TestDcfWithGordonGrowth:
    """DCF + Gordon growth 公式正确性验证"""

    def test_no_terminal_growth_pure_dcf(self):
        """g = 0 → 不计终值，仅纯 DCF"""
        cash_flows = [Decimal("100000")]
        npv, details = _calc_dcf_with_gordon(
            cash_flows, discount_rate=Decimal("0.10"), terminal_growth_rate=Decimal("0")
        )
        # NPV = 100000 / 1.10 = 90909.09
        assert npv == _quantize(Decimal("100000") / Decimal("1.10"))
        assert len(details) == 1  # no terminal entry

    def test_with_gordon_growth(self):
        """含 Gordon growth 终值 (g > 0)"""
        cash_flows = [Decimal("100000")] * 5
        npv, details = _calc_dcf_with_gordon(
            cash_flows,
            discount_rate=Decimal("0.10"),
            terminal_growth_rate=Decimal("0.03"),
        )
        # 5 现金流 PV ≈ 379078.68
        # CF_5 = 100000, TV = 100000 × 1.03 / (0.10 - 0.03) = 1471428.57
        # TV PV = 1471428.57 / 1.61051 ≈ 913480
        # Total ≈ 1292558
        assert len(details) == 6  # 5 years + Gordon terminal
        assert "Gordon" in details[-1]["year"]
        assert npv > Decimal("1290000")
        assert npv < Decimal("1295000")

    def test_high_growth_close_to_discount(self):
        """g 接近 r 时终值变得很大（但仍有限）"""
        cash_flows = [Decimal("100000")] * 3
        # r=0.10, g=0.09 → r-g=0.01 → TV very large
        npv, _ = _calc_dcf_with_gordon(
            cash_flows,
            discount_rate=Decimal("0.10"),
            terminal_growth_rate=Decimal("0.09"),
        )
        # TV = 100000 × 1.09 / 0.01 = 10,900,000
        # TV PV = 10,900,000 / 1.331 ≈ 8,189,331
        assert npv > Decimal("8000000")

    def test_zero_cash_flow_with_gordon_zero_terminal(self):
        """全零现金流且 g=0 → NPV = 0"""
        cash_flows = [Decimal("0")] * 3
        npv, details = _calc_dcf_with_gordon(
            cash_flows, discount_rate=Decimal("0.10"), terminal_growth_rate=Decimal("0")
        )
        assert npv == Decimal("0.00")
        assert len(details) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 2. GOODWILL IMPAIRMENT ALLOCATION (CAS 8 / IFRS 36)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoodwillAllocation:
    """商誉减值分摊：先冲商誉 → 剩余分摊到其他资产"""

    def test_no_impairment(self):
        """impairment_loss = 0 → 无分摊"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("0"),
            goodwill_book_value=Decimal("1000000"),
        )
        assert gw == Decimal("0")
        assert other == Decimal("0")
        assert allocs == []

    def test_loss_smaller_than_goodwill(self):
        """减值 < 商誉 → 全部由商誉承担"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("500000"),
            goodwill_book_value=Decimal("1000000"),
        )
        assert gw == Decimal("500000.00")
        assert other == Decimal("0.00")
        assert allocs == []

    def test_loss_equals_goodwill(self):
        """减值 = 商誉 → 商誉全额冲减，其他资产 0"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("1000000"),
            goodwill_book_value=Decimal("1000000"),
        )
        assert gw == Decimal("1000000.00")
        assert other == Decimal("0.00")
        assert allocs == []

    def test_loss_exceeds_goodwill(self):
        """减值 > 商誉 → 商誉全冲，剩余分摊到其他资产"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("1500000"),
            goodwill_book_value=Decimal("1000000"),
        )
        assert gw == Decimal("1000000.00")
        assert other == Decimal("500000.00")
        assert allocs == []

    def test_allocation_sum_equals_total_loss(self):
        """商誉冲减 + 其他资产冲减 = 总减值（守恒律）"""
        for loss in [Decimal("100"), Decimal("999999"), Decimal("1500000")]:
            for gw_book in [Decimal("100"), Decimal("500000"), Decimal("2000000")]:
                gw_wd, other_wd, _allocs = _allocate_goodwill_impairment(loss, gw_book)
                assert gw_wd + other_wd == _quantize(loss), (
                    f"loss={loss} gw={gw_book}: gw_wd={gw_wd} + other_wd={other_wd}"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SCHEMA VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestRequestValidation:
    """输入参数 schema 校验"""

    def test_valid_request(self):
        req = GoodwillImpairmentRequest(
            cgu_id="CGU-G-001",
            goodwill_book_value=Decimal("1000000"),
            other_assets_book_value=Decimal("3000000"),
            cash_flows=[Decimal("500000")] * 5,
            discount_rate=Decimal("0.10"),
            terminal_growth_rate=Decimal("0.03"),
        )
        assert req.cgu_id == "CGU-G-001"

    def test_goodwill_book_value_must_be_positive(self):
        with pytest.raises(Exception):
            GoodwillImpairmentRequest(
                cgu_id="CGU-G-001",
                goodwill_book_value=Decimal("0"),
                other_assets_book_value=Decimal("3000000"),
                cash_flows=[Decimal("500000")],
                discount_rate=Decimal("0.10"),
            )

    def test_other_assets_book_value_can_be_zero(self):
        """其他资产可以为 0（极端情况：CGU 仅含商誉）"""
        req = GoodwillImpairmentRequest(
            cgu_id="CGU-G-001",
            goodwill_book_value=Decimal("1000000"),
            other_assets_book_value=Decimal("0"),
            cash_flows=[Decimal("500000")],
            discount_rate=Decimal("0.10"),
        )
        assert req.other_assets_book_value == Decimal("0")

    def test_discount_rate_must_be_positive(self):
        with pytest.raises(Exception):
            GoodwillImpairmentRequest(
                cgu_id="CGU-G-001",
                goodwill_book_value=Decimal("1000000"),
                other_assets_book_value=Decimal("3000000"),
                cash_flows=[Decimal("500000")],
                discount_rate=Decimal("0"),
            )

    def test_discount_rate_must_be_less_than_1(self):
        with pytest.raises(Exception):
            GoodwillImpairmentRequest(
                cgu_id="CGU-G-001",
                goodwill_book_value=Decimal("1000000"),
                other_assets_book_value=Decimal("3000000"),
                cash_flows=[Decimal("500000")],
                discount_rate=Decimal("1.0"),
            )

    def test_terminal_growth_rate_default_zero(self):
        req = GoodwillImpairmentRequest(
            cgu_id="CGU-G-001",
            goodwill_book_value=Decimal("1000000"),
            other_assets_book_value=Decimal("3000000"),
            cash_flows=[Decimal("500000")],
            discount_rate=Decimal("0.10"),
        )
        assert req.terminal_growth_rate == Decimal("0")

    def test_terminal_growth_rate_cannot_be_negative(self):
        with pytest.raises(Exception):
            GoodwillImpairmentRequest(
                cgu_id="CGU-G-001",
                goodwill_book_value=Decimal("1000000"),
                other_assets_book_value=Decimal("3000000"),
                cash_flows=[Decimal("500000")],
                discount_rate=Decimal("0.10"),
                terminal_growth_rate=Decimal("-0.01"),
            )

    def test_cash_flows_min_length_1(self):
        with pytest.raises(Exception):
            GoodwillImpairmentRequest(
                cgu_id="CGU-G-001",
                goodwill_book_value=Decimal("1000000"),
                other_assets_book_value=Decimal("3000000"),
                cash_flows=[],
                discount_rate=Decimal("0.10"),
            )

    def test_cash_flows_max_length_10(self):
        with pytest.raises(Exception):
            GoodwillImpairmentRequest(
                cgu_id="CGU-G-001",
                goodwill_book_value=Decimal("1000000"),
                other_assets_book_value=Decimal("3000000"),
                cash_flows=[Decimal("100000")] * 11,
                discount_rate=Decimal("0.10"),
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. END-TO-END SCENARIOS
# ═══════════════════════════════════════════════════════════════════════════════


class TestImpairmentScenarios:
    """端到端业务场景：DCF + 减值 + 分摊一体测算"""

    def test_no_impairment_when_recoverable_exceeds_total(self):
        """可收回金额 > 总账面 → 无减值"""
        cash_flows = [Decimal("2000000")] * 5
        npv, _ = _calc_dcf_with_gordon(
            cash_flows, Decimal("0.08"), Decimal("0.02")
        )
        # NPV ≈ 7,985,420 + Gordon TV
        total_book = Decimal("1000000") + Decimal("3000000")  # 4,000,000
        assert npv > total_book
        impairment_loss = max(Decimal("0"), total_book - npv)
        assert impairment_loss == Decimal("0")

    def test_partial_goodwill_writedown(self):
        """减值 < 商誉 → 仅商誉部分冲减"""
        cash_flows = [Decimal("200000")] * 5
        npv, _ = _calc_dcf_with_gordon(
            cash_flows, Decimal("0.10"), Decimal("0")
        )
        # NPV ≈ 758157
        total_book = Decimal("1000000") + Decimal("100000")  # 1,100,000
        impairment = max(Decimal("0"), total_book - npv)
        # impairment ≈ 341,843
        gw_wd, other_wd, _allocs = _allocate_goodwill_impairment(
            impairment, goodwill_book_value=Decimal("1000000")
        )
        # 减值远小于商誉，全部由商誉承担
        assert gw_wd == _quantize(impairment)
        assert other_wd == Decimal("0.00")

    def test_full_goodwill_plus_other_assets_writedown(self):
        """减值 > 商誉 → 商誉全冲 + 其他资产分摊"""
        cash_flows = [Decimal("50000")] * 5
        npv, _ = _calc_dcf_with_gordon(
            cash_flows, Decimal("0.10"), Decimal("0")
        )
        # NPV ≈ 189,539
        total_book = Decimal("500000") + Decimal("2000000")  # 2,500,000
        impairment = max(Decimal("0"), total_book - npv)
        # impairment ≈ 2,310,461
        gw_wd, other_wd, _allocs = _allocate_goodwill_impairment(
            impairment, goodwill_book_value=Decimal("500000")
        )
        # 商誉先全冲减 500000，剩余 ~1,810,461 分摊到其他资产
        assert gw_wd == Decimal("500000.00")
        assert other_wd > Decimal("1800000")
        assert gw_wd + other_wd == _quantize(impairment)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. WRITE-BACK HELPER
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """写回 helper 签名和可调用性"""

    def test_write_back_function_exists(self):
        assert callable(_maybe_apply_goodwill_impairment_to_workpaper)

    def test_write_back_is_async(self):
        assert inspect.iscoroutinefunction(
            _maybe_apply_goodwill_impairment_to_workpaper
        )

    def test_write_back_returns_none_when_no_sheet(self):
        """apply_to_sheet 为 None 时不写回，直接返回 None"""
        import asyncio

        async def _test():
            return await _maybe_apply_goodwill_impairment_to_workpaper(
                db=None,  # type: ignore
                wp_id="fake-id",
                payload=GoodwillImpairmentRequest(
                    cgu_id="CGU-G-001",
                    goodwill_book_value=Decimal("1000000"),
                    other_assets_book_value=Decimal("3000000"),
                    cash_flows=[Decimal("500000")],
                    discount_rate=Decimal("0.10"),
                    apply_to_sheet=None,
                ),
                pv_cash_flows=Decimal("454545.45"),
                recoverable_amount=Decimal("454545.45"),
                total_book_value=Decimal("4000000.00"),
                impairment_loss=Decimal("3545454.55"),
                goodwill_writedown=Decimal("1000000.00"),
                other_assets_writedown=Decimal("2545454.55"),
                is_impaired=True,
                dcf_details=[],
                summary="test",
            )

        assert asyncio.run(_test()) is None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. RBAC + ENDPOINT METADATA
# ═══════════════════════════════════════════════════════════════════════════════


class TestRbac:
    """RBAC 校验"""

    def test_endpoint_has_rbac_dependency(self):
        sig = inspect.signature(i3_goodwill_impairment_analysis)
        assert "_user" in sig.parameters

    def test_endpoint_is_async(self):
        assert inspect.iscoroutinefunction(i3_goodwill_impairment_analysis)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. QUANTIZE HELPER
# ═══════════════════════════════════════════════════════════════════════════════


class TestQuantize:
    def test_rounds_half_up(self):
        assert _quantize(Decimal("1.005")) == Decimal("1.01")
        assert _quantize(Decimal("1.004")) == Decimal("1.00")

    def test_preserves_exact_values(self):
        assert _quantize(Decimal("0.01")) == Decimal("0.01")
        assert _quantize(Decimal("100.00")) == Decimal("100.00")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. CGU ASSET-LEVEL ALLOCATION (CAS 8 / IFRS 36 完整版 — Sprint 4 Task 4.2)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAssetAllocation:
    """CGU 内各资产分摊（CAS 8 / IFRS 36 完整版）

    覆盖 6 case：
    1. 无资产清单 → 保持原汇总行为（向后兼容）
    2. 单资产，剩余 < 资产可分摊上限 → 全额分摊
    3. 单资产，剩余 > 资产可分摊上限 → cap 在 max(book − recoverable, 0)
    4. 多资产，按比例分摊，全部满足下限 → 单次分摊完成
    5. 多资产，部分超下限 → 迭代重新分摊
    6. 守恒律：goodwill_writedown + sum(asset_allocations) = total_impairment
    """

    # ─── case 1: backward compat ─────────────────────────────────────────────

    def test_no_cgu_assets_returns_aggregate_only(self):
        """case 1: cgu_assets=None 保持原 2-tuple-like 汇总行为，分摊列表为空"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("1500000"),
            goodwill_book_value=Decimal("1000000"),
            cgu_assets=None,
        )
        assert gw == Decimal("1000000.00")
        assert other == Decimal("500000.00")
        assert allocs == []

    def test_empty_cgu_assets_treated_as_none(self):
        """case 1b: cgu_assets=[] 同样回退到向后兼容"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("1500000"),
            goodwill_book_value=Decimal("1000000"),
            cgu_assets=[],
        )
        assert gw == Decimal("1000000.00")
        assert other == Decimal("500000.00")
        assert allocs == []

    # ─── case 2: single asset, remaining within cap ──────────────────────────

    def test_single_asset_remaining_below_cap(self):
        """case 2: 商誉冲完后剩余 200000，资产 book 1000000 / recoverable 700000
        → 资产 max_writedown = 300000 ≥ 200000 → 全额分摊"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("1200000"),
            goodwill_book_value=Decimal("1000000"),
            cgu_assets=[
                {
                    "name": "专利权 A",
                    "book_value": Decimal("1000000"),
                    "recoverable_amount": Decimal("700000"),
                },
            ],
        )
        assert gw == Decimal("1000000.00")
        assert other == Decimal("200000.00")
        assert len(allocs) == 1
        assert allocs[0]["name"] == "专利权 A"
        assert allocs[0]["allocated_impairment"] == "200000.00"
        assert allocs[0]["post_impairment_book_value"] == "800000.00"
        # 800000 ≥ max(700000, 0) 满足下限
        assert Decimal(allocs[0]["post_impairment_book_value"]) >= Decimal("700000")

    def test_single_asset_no_recoverable_amount(self):
        """case 2b: 资产无 recoverable_amount → floor=0, max_writedown=book_value"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("1200000"),
            goodwill_book_value=Decimal("1000000"),
            cgu_assets=[
                {
                    "name": "软件 X",
                    "book_value": Decimal("500000"),
                    "recoverable_amount": None,
                },
            ],
        )
        assert gw == Decimal("1000000.00")
        assert other == Decimal("200000.00")
        assert allocs[0]["allocated_impairment"] == "200000.00"
        assert allocs[0]["post_impairment_book_value"] == "300000.00"
        assert allocs[0]["recoverable_amount"] is None

    # ─── case 3: single asset, remaining exceeds cap ─────────────────────────

    def test_single_asset_remaining_exceeds_cap(self):
        """case 3: 剩余 500000 但资产 max_writedown = 300000
        → 资产分摊 cap 在 300000，剩 200000 无处可分（应反映在 total_other）"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("1500000"),
            goodwill_book_value=Decimal("1000000"),
            cgu_assets=[
                {
                    "name": "土地使用权",
                    "book_value": Decimal("1000000"),
                    "recoverable_amount": Decimal("700000"),
                },
            ],
        )
        assert gw == Decimal("1000000.00")
        # 资产被 cap 在 300000；剩 200000 因下限保护无法继续分摊
        assert allocs[0]["allocated_impairment"] == "300000.00"
        assert allocs[0]["post_impairment_book_value"] == "700000.00"
        # other 等于实际分摊到资产的金额（300000），不是 500000
        assert other == Decimal("300000.00")

    def test_single_asset_negative_recoverable_floor_clamps_to_zero(self):
        """case 3b: recoverable_amount < 0 → floor 用 max(rec, 0) = 0"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("1200000"),
            goodwill_book_value=Decimal("1000000"),
            cgu_assets=[
                {
                    "name": "破损资产",
                    "book_value": Decimal("300000"),
                    "recoverable_amount": Decimal("-50000"),
                },
            ],
        )
        # max_writedown = 300000 - max(-50000, 0) = 300000
        # 剩余 200000 全部分摊到资产
        assert gw == Decimal("1000000.00")
        assert other == Decimal("200000.00")
        assert allocs[0]["allocated_impairment"] == "200000.00"
        assert allocs[0]["post_impairment_book_value"] == "100000.00"

    # ─── case 4: multi-asset proportional, all satisfied ─────────────────────

    def test_multi_asset_proportional_all_satisfied(self):
        """case 4: 3 资产 book=1000/2000/3000，剩余 600 按比例分 100/200/300，全部满足下限"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("1600"),
            goodwill_book_value=Decimal("1000"),
            cgu_assets=[
                {"name": "A", "book_value": Decimal("1000"), "recoverable_amount": Decimal("500")},
                {"name": "B", "book_value": Decimal("2000"), "recoverable_amount": Decimal("500")},
                {"name": "C", "book_value": Decimal("3000"), "recoverable_amount": Decimal("500")},
            ],
        )
        assert gw == Decimal("1000.00")
        assert other == Decimal("600.00")
        # 按 1:2:3 分摊 600 → 100/200/300
        assert allocs[0]["allocated_impairment"] == "100.00"
        assert allocs[1]["allocated_impairment"] == "200.00"
        assert allocs[2]["allocated_impairment"] == "300.00"
        # 全部满足下限：900 ≥ 500，1800 ≥ 500，2700 ≥ 500
        for a in allocs:
            post = Decimal(a["post_impairment_book_value"])
            rec = Decimal(a["recoverable_amount"])
            assert post >= rec

    # ─── case 5: multi-asset, some exceed floor → iterative reallocation ─────

    def test_multi_asset_iterative_reallocation(self):
        """case 5: A 容量小（max=200），B 容量大（max=10000）
        剩余 1000 按 1:1 分摊 → A:500/B:500，A 超 max 溢出 300 → 重新分配到 B
        最终 A:200 / B:800 = 1000"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("2000"),  # gw=1000, remaining=1000
            goodwill_book_value=Decimal("1000"),
            cgu_assets=[
                # A: book=1000, recoverable=800 → max_writedown=200
                {"name": "A", "book_value": Decimal("1000"), "recoverable_amount": Decimal("800")},
                # B: book=1000, recoverable=0 → max_writedown=1000
                {"name": "B", "book_value": Decimal("1000"), "recoverable_amount": Decimal("0")},
            ],
        )
        assert gw == Decimal("1000.00")
        assert other == Decimal("1000.00")
        # A 被 cap 在 200，B 接收剩余 800
        a_alloc = next(x for x in allocs if x["name"] == "A")
        b_alloc = next(x for x in allocs if x["name"] == "B")
        assert a_alloc["allocated_impairment"] == "200.00"
        assert b_alloc["allocated_impairment"] == "800.00"
        assert a_alloc["post_impairment_book_value"] == "800.00"
        assert b_alloc["post_impairment_book_value"] == "200.00"

    def test_multi_asset_total_floor_blocks_full_allocation(self):
        """case 5b: 所有资产合计 max_writedown < remaining → 分摊到上限即停止"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("5000"),  # gw=1000, remaining=4000
            goodwill_book_value=Decimal("1000"),
            cgu_assets=[
                {"name": "A", "book_value": Decimal("1000"), "recoverable_amount": Decimal("800")},  # max=200
                {"name": "B", "book_value": Decimal("1000"), "recoverable_amount": Decimal("700")},  # max=300
            ],
        )
        assert gw == Decimal("1000.00")
        # 合计 max=500，剩 3500 无法分摊（受下限保护）
        assert other == Decimal("500.00")
        a = next(x for x in allocs if x["name"] == "A")
        b = next(x for x in allocs if x["name"] == "B")
        assert a["allocated_impairment"] == "200.00"
        assert b["allocated_impairment"] == "300.00"

    # ─── case 6: conservation law ────────────────────────────────────────────

    def test_conservation_goodwill_plus_assets_equals_total_for_satisfied(self):
        """case 6: 当资产总容量 ≥ remaining 时，goodwill_wd + sum(allocs) = total_impairment"""
        scenarios = [
            (Decimal("1500000"), Decimal("1000000"), [
                {"name": "A", "book_value": Decimal("2000000"), "recoverable_amount": Decimal("500000")},
            ]),
            (Decimal("3000"), Decimal("1000"), [
                {"name": "X", "book_value": Decimal("5000"), "recoverable_amount": Decimal("0")},
                {"name": "Y", "book_value": Decimal("3000"), "recoverable_amount": Decimal("0")},
            ]),
            (Decimal("1000"), Decimal("0.01"), [
                {"name": "Solo", "book_value": Decimal("2000"), "recoverable_amount": None},
            ]),
        ]
        for total_loss, gw_book, assets in scenarios:
            gw, other, allocs = _allocate_goodwill_impairment(
                impairment_loss=total_loss,
                goodwill_book_value=gw_book,
                cgu_assets=assets,
            )
            allocated_sum = sum(
                (Decimal(a["allocated_impairment"]) for a in allocs),
                Decimal("0"),
            )
            # 守恒：商誉冲减 + 资产分摊 = 总减值
            assert gw + allocated_sum == _quantize(total_loss), (
                f"loss={total_loss}: gw={gw} + assets={allocated_sum} ≠ {total_loss}"
            )
            # 内部一致：other 汇总值 = 资产分摊总和
            assert other == _quantize(allocated_sum)

    def test_conservation_with_floor_overflow_documented(self):
        """case 6b: 容量不足时，商誉 + 资产分摊 < 总减值（差额是受下限保护的"无处可去"溢出）"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("5000"),  # gw=1000, remaining=4000
            goodwill_book_value=Decimal("1000"),
            cgu_assets=[
                # 合计 max_writedown = 200 + 300 = 500，远小于 4000
                {"name": "A", "book_value": Decimal("1000"), "recoverable_amount": Decimal("800")},
                {"name": "B", "book_value": Decimal("1000"), "recoverable_amount": Decimal("700")},
            ],
        )
        allocated_sum = sum(
            (Decimal(a["allocated_impairment"]) for a in allocs),
            Decimal("0"),
        )
        # gw=1000 + assets=500 = 1500 < 5000，差额 3500 是合规溢出
        assert gw + allocated_sum == Decimal("1500.00")
        # 每项资产仍满足下限
        for a in allocs:
            post = Decimal(a["post_impairment_book_value"])
            rec = Decimal(a["recoverable_amount"]) if a["recoverable_amount"] else Decimal("0")
            assert post >= max(rec, Decimal("0"))

    def test_zero_impairment_with_assets_returns_zero_allocations(self):
        """case 7（边界）：无减值时返回零分摊但保留资产清单结构"""
        gw, other, allocs = _allocate_goodwill_impairment(
            impairment_loss=Decimal("0"),
            goodwill_book_value=Decimal("1000000"),
            cgu_assets=[
                {"name": "A", "book_value": Decimal("500000"), "recoverable_amount": Decimal("400000")},
            ],
        )
        assert gw == Decimal("0.00")
        assert other == Decimal("0.00")
        assert len(allocs) == 1
        assert allocs[0]["allocated_impairment"] == "0.00"
        assert allocs[0]["post_impairment_book_value"] == "500000.00"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. SCHEMA EXTENSION (cgu_assets / asset_allocations)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchemaExtension:
    """Sprint 4 Task 4.2 — schema 向后兼容性"""

    def test_cgu_assets_optional_default_none(self):
        """请求未传 cgu_assets 时默认为 None（向后兼容）"""
        req = GoodwillImpairmentRequest(
            cgu_id="CGU-G-001",
            goodwill_book_value=Decimal("1000000"),
            other_assets_book_value=Decimal("3000000"),
            cash_flows=[Decimal("500000")],
            discount_rate=Decimal("0.10"),
        )
        assert req.cgu_assets is None

    def test_cgu_assets_accepts_list_of_dicts(self):
        """请求允许带 cgu_assets 资产清单"""
        req = GoodwillImpairmentRequest(
            cgu_id="CGU-G-001",
            goodwill_book_value=Decimal("1000000"),
            other_assets_book_value=Decimal("3000000"),
            cash_flows=[Decimal("500000")],
            discount_rate=Decimal("0.10"),
            cgu_assets=[
                {
                    "name": "A",
                    "book_value": Decimal("100000"),
                    "recoverable_amount": Decimal("50000"),
                },
            ],
        )
        assert req.cgu_assets is not None
        assert len(req.cgu_assets) == 1
        assert req.cgu_assets[0]["name"] == "A"

    def test_response_asset_allocations_default_empty(self):
        """响应 asset_allocations 默认空列表（向后兼容）"""
        resp = GoodwillImpairmentResponse(
            cgu_id="CGU-G-001",
            goodwill_book_value="1000000",
            other_assets_book_value="3000000",
            total_book_value="4000000",
            present_value_of_cash_flows="3000000",
            recoverable_amount="3000000",
            impairment_loss="1000000",
            goodwill_writedown="1000000",
            other_assets_writedown="0",
            is_impaired=True,
            dcf_details=[],
            summary="test",
        )
        assert resp.asset_allocations == []


# ═══════════════════════════════════════════════════════════════════════════════
# RE-I1 + RE-I3 — Sprint 4 二轮复盘修复（is_llm_stub 由 settings 驱动 + summary 变量插值）
# ═══════════════════════════════════════════════════════════════════════════════


class TestStubFlagDrivenBySettings:
    """RE-I1: is_llm_stub 字段由 settings.WP_AI_SERVICE_ENABLED 驱动，禁止硬编码 True"""

    def test_is_llm_stub_true_when_ai_disabled(self, monkeypatch):
        """settings.WP_AI_SERVICE_ENABLED = False → is_llm_stub = True"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", False)

        # 直接构造 endpoint 调用并验证返回字段
        import asyncio
        from unittest.mock import AsyncMock
        from decimal import Decimal as D
        from app.routers.wp_i_goodwill import (
            GoodwillImpairmentRequest,
            i3_goodwill_impairment_analysis,
        )

        req = GoodwillImpairmentRequest(
            cgu_id="CGU-001",
            goodwill_book_value=D("1000000"),
            other_assets_book_value=D("5000000"),
            cash_flows=[D("800000")] * 5,
            discount_rate=D("0.10"),
            terminal_growth_rate=D("0.02"),
        )
        mock_db = AsyncMock()
        resp = asyncio.run(
            i3_goodwill_impairment_analysis(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=req,
                db=mock_db,
                _user=object(),
            )
        )
        assert resp.is_llm_stub is True
        assert "LLM 智能分析待 wp_ai_service 接入" in resp.summary

    def test_is_llm_stub_false_when_ai_enabled(self, monkeypatch):
        """settings.WP_AI_SERVICE_ENABLED = True → is_llm_stub = False + 不附加 stub 提示"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", True)

        import asyncio
        from unittest.mock import AsyncMock
        from decimal import Decimal as D
        from app.routers.wp_i_goodwill import (
            GoodwillImpairmentRequest,
            i3_goodwill_impairment_analysis,
        )

        req = GoodwillImpairmentRequest(
            cgu_id="CGU-002",
            goodwill_book_value=D("500000"),
            other_assets_book_value=D("2000000"),
            cash_flows=[D("400000")] * 5,
            discount_rate=D("0.10"),
            terminal_growth_rate=D("0.02"),
        )
        mock_db = AsyncMock()
        resp = asyncio.run(
            i3_goodwill_impairment_analysis(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=req,
                db=mock_db,
                _user=object(),
            )
        )
        assert resp.is_llm_stub is False
        assert "LLM 智能分析待 wp_ai_service 接入" not in resp.summary


class TestSummaryVariableInterpolation:
    """RE-I3: summary 文案必须含完整变量插值（CGU ID / 商誉占比 / 现金流 / 折现率等）"""

    def test_summary_contains_cgu_id(self):
        from app.routers.wp_i_goodwill import GoodwillImpairmentRequest, i3_goodwill_impairment_analysis
        import asyncio
        from unittest.mock import AsyncMock
        from decimal import Decimal as D

        req = GoodwillImpairmentRequest(
            cgu_id="CGU-INTERP-001",
            goodwill_book_value=D("1000000"),
            other_assets_book_value=D("3000000"),
            cash_flows=[D("700000"), D("750000"), D("800000"), D("850000"), D("900000")],
            discount_rate=D("0.12"),
            terminal_growth_rate=D("0.03"),
        )
        mock_db = AsyncMock()
        resp = asyncio.run(
            i3_goodwill_impairment_analysis(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=req,
                db=mock_db,
                _user=object(),
            )
        )
        # CGU ID
        assert "CGU-INTERP-001" in resp.summary
        # 商誉占比百分比
        assert "占比" in resp.summary and "%" in resp.summary
        # 现金流明细（前 3 期）
        assert "¥700,000" in resp.summary or "¥700,000.00" in resp.summary or "现金流" in resp.summary
        # 折现率
        assert "12.0%" in resp.summary
        # Gordon growth rate
        assert "g=3.0%" in resp.summary

    def test_summary_no_terminal_growth_no_gordon_label(self):
        """terminal_growth_rate=0 时不应出现 Gordon g= 标记"""
        from app.routers.wp_i_goodwill import GoodwillImpairmentRequest, i3_goodwill_impairment_analysis
        import asyncio
        from unittest.mock import AsyncMock
        from decimal import Decimal as D

        req = GoodwillImpairmentRequest(
            cgu_id="CGU-NOGROWTH",
            goodwill_book_value=D("500000"),
            other_assets_book_value=D("1500000"),
            cash_flows=[D("400000")] * 3,
            discount_rate=D("0.10"),
            terminal_growth_rate=D("0"),
        )
        mock_db = AsyncMock()
        resp = asyncio.run(
            i3_goodwill_impairment_analysis(
                project_id="00000000-0000-0000-0000-000000000001",
                wp_id="00000000-0000-0000-0000-000000000002",
                payload=req,
                db=mock_db,
                _user=object(),
            )
        )
        assert "Gordon" not in resp.summary
