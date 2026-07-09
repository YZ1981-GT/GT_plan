"""N1 递延所得税资产 — 后端集成测试 (Task 7.2).

覆盖：
1. 模块导入测试：renderer / router / service 均可导入
2. RENDERER_DISPATCH 注册验证
3. wp_code_overrides 覆盖(9条目: N1/N1-1~N1-5/N1A)
4. 路由注册(3端点存在)
5. 资产类取数逻辑（期末=期初+借方-贷方）
6. 递延所得税测算引擎（差异×税率+分类）
7. 可弥补亏损确认引擎（谨慎性限额）
8. 跨底稿合计（N1+N3→N5递延所得税费用）

Spec: .kiro/specs/n1-deferred-tax-assets/ Task 7.2
Requirements: 2.5-2.6, 4.4, 5.5, 7.1-7.5, 8.1-8.4

科目：1811 递延所得税资产（**借方/资产类！期末=期初+借方-贷方**）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1: 模块导入测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestN1Imports:
    """renderer, router, service 均可导入（无语法错误/循环依赖）"""

    def test_renderer_importable(self):
        """渲染策略可导入"""
        from app.routers.wp_render_strategies._n1_deferred_tax_assets import render  # noqa: F401
        assert callable(render)

    def test_router_importable(self):
        """路由模块可导入"""
        from app.routers.n1_deferred_tax_assets import router  # noqa: F401
        assert router is not None

    def test_service_importable(self):
        """服务模块可导入"""
        from app.services.n1_deferred_tax_assets_service import (
            calc_asset_end_balance,
            calc_audited_amount,
            calc_temporary_difference,
            calc_deferred_tax,
            calc_deferred_tax_asset,
            calc_unrecovered_loss,
            calc_recognizable_asset,
            is_compensation_expired,
            classify_temporary_differences,
            calc_loss_recognition,
        )
        assert callable(calc_asset_end_balance)
        assert callable(calc_audited_amount)
        assert callable(calc_temporary_difference)
        assert callable(calc_deferred_tax)
        assert callable(calc_deferred_tax_asset)
        assert callable(calc_unrecovered_loss)
        assert callable(calc_recognizable_asset)
        assert callable(is_compensation_expired)
        assert callable(classify_temporary_differences)
        assert callable(calc_loss_recognition)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: RENDERER_DISPATCH 集成
# ═══════════════════════════════════════════════════════════════════════════════


class TestRendererDispatch:
    """验证 n1-deferred-tax-assets 在 RENDERER_DISPATCH 中注册"""

    def test_renderer_dispatch_contains_n1(self):
        """RENDERER_DISPATCH 有 n1-deferred-tax-assets 条目"""
        from app.routers.wp_render_strategies import RENDERER_DISPATCH
        assert "n1-deferred-tax-assets" in RENDERER_DISPATCH

    def test_renderer_dispatch_value_is_callable(self):
        """RENDERER_DISPATCH['n1-deferred-tax-assets'] 是可调用的 render 函数"""
        from app.routers.wp_render_strategies import RENDERER_DISPATCH
        fn = RENDERER_DISPATCH["n1-deferred-tax-assets"]
        assert callable(fn)

    def test_renderer_dispatch_value_is_correct_function(self):
        """RENDERER_DISPATCH 指向正确的 render 函数"""
        from app.routers.wp_render_strategies import RENDERER_DISPATCH
        from app.routers.wp_render_strategies._n1_deferred_tax_assets import render
        assert RENDERER_DISPATCH["n1-deferred-tax-assets"] is render


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3: wp_code_overrides 覆盖 (N1系列9条目)
# ═══════════════════════════════════════════════════════════════════════════════


class TestWpCodeOverrides:
    """验证 wp_code_overrides.json 中 N1 系列映射"""

    @pytest.fixture(scope="class")
    def overrides(self) -> dict[str, str]:
        """加载 wp_code_overrides.json"""
        overrides_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "data"
            / "wp_code_overrides.json"
        )
        assert overrides_path.exists(), f"wp_code_overrides.json 不存在: {overrides_path}"
        with open(overrides_path, encoding="utf-8") as f:
            return json.load(f)

    @pytest.mark.parametrize(
        "wp_code",
        [
            "N1",
            "N1-1",
            "N1-2",
            "N1-3",
            "N1-4",
            "N1-5",
            "N1A",
        ],
    )
    def test_n1_wp_code_mapped(self, overrides: dict, wp_code: str):
        """N1系列wp_code均映射到n1-deferred-tax-assets"""
        assert wp_code in overrides, f"wp_code '{wp_code}' 不在 overrides 中"
        assert overrides[wp_code] == "n1-deferred-tax-assets"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4: 资产类取数逻辑 (Req 8.1-8.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAssetEndBalance:
    """资产类期末余额 = 期初 + 借方 - 贷方（Req 8.1）"""

    def test_basic_asset_end_balance(self):
        """期初1000万+借500万-贷200万 = 1300万"""
        from app.services.n1_deferred_tax_assets_service import calc_asset_end_balance
        result = calc_asset_end_balance(10_000_000, 5_000_000, 2_000_000)
        assert result == 13_000_000

    def test_zero_begin_debit_only(self):
        """零期初+仅借方 → 期末=借方"""
        from app.services.n1_deferred_tax_assets_service import calc_asset_end_balance
        result = calc_asset_end_balance(0, 3_000_000, 0)
        assert result == 3_000_000

    def test_full_reversal(self):
        """全额转回 → 期末=0"""
        from app.services.n1_deferred_tax_assets_service import calc_asset_end_balance
        result = calc_asset_end_balance(5_000_000, 0, 5_000_000)
        assert result == 0

    def test_asset_vs_liability_direction(self):
        """资产类 vs 负债类方向不同验证"""
        from app.services.n1_deferred_tax_assets_service import calc_asset_end_balance
        begin, debit, credit = 5_000_000, 3_000_000, 1_000_000
        asset_end = calc_asset_end_balance(begin, debit, credit)
        liability_end = begin + credit - debit  # 负债类
        assert asset_end == 7_000_000
        assert liability_end == 3_000_000
        assert asset_end != liability_end

    def test_validate_asset_direction(self):
        """validate_asset_direction 校验通过"""
        from app.services.n1_deferred_tax_assets_service import validate_asset_direction
        result = validate_asset_direction(10_000_000, 5_000_000, 2_000_000, 13_000_000)
        assert result["isValid"] is True
        assert result["direction"] == "debit"
        assert result["account_code"] == "1811"

    def test_validate_asset_direction_mismatch(self):
        """validate_asset_direction 校验失败（报告值不等于计算值）"""
        from app.services.n1_deferred_tax_assets_service import validate_asset_direction
        result = validate_asset_direction(10_000_000, 5_000_000, 2_000_000, 14_000_000)
        assert result["isValid"] is False
        assert result["difference"] == 1_000_000


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5: 递延所得税测算引擎 (Req 4.2-4.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeferredTaxEngine:
    """递延所得税 = 暂时性差异 × 适用税率"""

    def test_temporary_difference(self):
        """暂时性差异 = 账面价值 - 计税基础"""
        from app.services.n1_deferred_tax_assets_service import calc_temporary_difference
        assert calc_temporary_difference(1_000_000, 1_500_000) == -500_000  # 可抵扣
        assert calc_temporary_difference(2_000_000, 1_500_000) == 500_000   # 应纳税
        assert calc_temporary_difference(1_000_000, 1_000_000) == 0          # 无差异

    def test_deferred_tax(self):
        """递延所得税 = 差异 × 税率"""
        from app.services.n1_deferred_tax_assets_service import calc_deferred_tax
        assert calc_deferred_tax(2_000_000, 0.25) == 500_000
        assert calc_deferred_tax(-500_000, 0.25) == -125_000
        assert calc_deferred_tax(0, 0.25) == 0

    def test_deferred_tax_asset(self):
        """递延所得税资产 = 可抵扣差异 × 税率"""
        from app.services.n1_deferred_tax_assets_service import calc_deferred_tax_asset
        assert calc_deferred_tax_asset(500_000, 0.25) == 125_000
        assert calc_deferred_tax_asset(3_000_000, 0.15) == 450_000

    def test_classify_temporary_differences(self):
        """分类暂时性差异：可抵扣→N1资产，应纳税→N3负债"""
        from app.services.n1_deferred_tax_assets_service import classify_temporary_differences
        rows = [
            {"bookValue": 1_000_000, "taxBase": 1_500_000, "name": "资产减值"},   # 可抵扣
            {"bookValue": 2_000_000, "taxBase": 1_500_000, "name": "公允价值"},   # 应纳税
            {"bookValue": 800_000, "taxBase": 1_000_000, "name": "预提费用"},     # 可抵扣
            {"bookValue": 1_000_000, "taxBase": 1_000_000, "name": "无差异"},     # 无
        ]
        result = classify_temporary_differences(rows)
        assert len(result["deductible"]) == 2  # 资产减值+预提费用→N1
        assert len(result["taxable"]) == 1     # 公允价值→N3
        # 验证可抵扣差异绝对值
        assert result["deductible"][0]["deductibleDiff"] == 500_000
        assert result["deductible"][1]["deductibleDiff"] == 200_000
        # 验证应纳税差异
        assert result["taxable"][0]["taxableDiff"] == 500_000

    def test_weighted_avg_rate(self):
        """加权平均税率验证"""
        from app.services.n1_deferred_tax_assets_service import calc_weighted_avg_rate
        tax_amounts = [500_000, 150_000, 125_000]
        diffs = [2_000_000, 1_000_000, 500_000]
        expected = sum(tax_amounts) / sum(diffs)
        assert abs(calc_weighted_avg_rate(tax_amounts, diffs) - expected) < 1e-10

    def test_weighted_avg_rate_zero_diffs(self):
        """差异合计=0时返回0"""
        from app.services.n1_deferred_tax_assets_service import calc_weighted_avg_rate
        assert calc_weighted_avg_rate([0, 0], [0, 0]) == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6: 可弥补亏损确认引擎 (Req 5.2-5.5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestLossCompensationEngine:
    """可弥补亏损确认：min(未弥补亏损, 预计未来所得额)×税率"""

    def test_unrecovered_loss(self):
        """未弥补亏损 = 亏损 - 已弥补"""
        from app.services.n1_deferred_tax_assets_service import calc_unrecovered_loss
        assert calc_unrecovered_loss(10_000_000, 2_000_000) == 8_000_000
        assert calc_unrecovered_loss(5_000_000, 5_000_000) == 0
        assert calc_unrecovered_loss(3_000_000, 5_000_000) == 0  # 不允许负值

    def test_recognizable_asset(self):
        """可确认递延税资产 = min(未弥补, 未来所得额) × 税率"""
        from app.services.n1_deferred_tax_assets_service import calc_recognizable_asset
        # 未弥补800万, 未来所得500万 → min(800,500)×25%=125万
        assert calc_recognizable_asset(8_000_000, 5_000_000, 0.25) == 1_250_000
        # 未弥补200万, 未来所得500万 → min(200,500)×25%=50万
        assert calc_recognizable_asset(2_000_000, 5_000_000, 0.25) == 500_000

    def test_compensation_expired(self):
        """弥补期限届满判断"""
        from app.services.n1_deferred_tax_assets_service import is_compensation_expired
        # 2019年亏损, 2025年审计, 5年 → 2025-2019=6>5 → 届满
        assert is_compensation_expired(2019, 2025, 5) is True
        # 2020年亏损, 2025年审计, 5年 → 2025-2020=5=5 → 未届满
        assert is_compensation_expired(2020, 2025, 5) is False
        # 高新10年：2016年, 2025年 → 2025-2016=9<10 → 未届满
        assert is_compensation_expired(2016, 2025, 10) is False

    def test_loss_recognition_batch(self):
        """批量亏损确认计算"""
        from app.services.n1_deferred_tax_assets_service import calc_loss_recognition
        losses = [
            {"lossYear": 2021, "lossAmount": 5_000_000, "recovered": 1_000_000, "maxYears": 5},
            {"lossYear": 2022, "lossAmount": 3_000_000, "recovered": 500_000, "maxYears": 5},
        ]
        result = calc_loss_recognition(losses, 10_000_000, 0.25)
        assert result["totalUnrecovered"] > 0
        assert result["totalRecognizable"] > 0
        assert result["insufficientWarning"] is False
        assert len(result["details"]) == 2

    def test_loss_recognition_insufficient_income(self):
        """未来所得额不足 → insufficientWarning=True"""
        from app.services.n1_deferred_tax_assets_service import calc_loss_recognition
        losses = [
            {"lossYear": 2023, "lossAmount": 20_000_000, "recovered": 0, "maxYears": 5},
        ]
        result = calc_loss_recognition(losses, 5_000_000, 0.25)
        assert result["insufficientWarning"] is True
        assert result["totalUnrecovered"] == 20_000_000


# ═══════════════════════════════════════════════════════════════════════════════
# Section 7: 跨底稿合计逻辑 (Req 7.1-7.5, 4.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossWorkpaperTotals:
    """N1+N3→N5 递延所得税费用核对逻辑"""

    def test_deferred_tax_expense_formula(self):
        """递延所得税费用 = N3本期变动 - N1本期变动"""
        # N1变动(资产增加300万): 费用=-300万（资产增加减少费用）
        # N3变动(负债增加200万): 费用=+200万（负债增加增加费用）
        n1_change = 3_000_000
        n3_change = 2_000_000
        deferred_tax_expense = n3_change - n1_change
        assert deferred_tax_expense == -1_000_000

    def test_n1_n3_correspondence_asset_liability_split(self):
        """N1-4同源测算：可抵扣→N1资产 / 应纳税→N3负债"""
        from app.services.n1_deferred_tax_assets_service import (
            classify_temporary_differences,
            calc_deferred_tax_asset,
        )
        rows = [
            {"bookValue": 5_000_000, "taxBase": 8_000_000},   # 可抵扣300万
            {"bookValue": 10_000_000, "taxBase": 7_000_000},  # 应纳税300万
            {"bookValue": 2_000_000, "taxBase": 3_000_000},   # 可抵扣100万
        ]
        classified = classify_temporary_differences(rows)
        # 可抵扣部分（→N1）: 300万+100万=400万
        total_deductible = sum(r["deductibleDiff"] for r in classified["deductible"])
        assert total_deductible == 4_000_000
        # 应纳税部分（→N3）: 300万
        total_taxable = sum(r["taxableDiff"] for r in classified["taxable"])
        assert total_taxable == 3_000_000
        # 递延税资产合计
        total_asset = calc_deferred_tax_asset(total_deductible, 0.25)
        assert total_asset == 1_000_000

    def test_period_change_for_n5(self):
        """本期变动额 = 期末 - 期初（供N5核对）"""
        from app.services.n1_deferred_tax_assets_service import calc_asset_end_balance
        begin = 10_000_000
        end = calc_asset_end_balance(begin, 5_000_000, 2_000_000)
        change = end - begin
        assert change == 3_000_000

    def test_audited_amount_writeback_payload(self):
        """审定数 = 未审 + AJE + RJE → 回写 trial_balance 期末余额"""
        from app.services.n1_deferred_tax_assets_service import calc_audited_amount
        audited = calc_audited_amount(12_000_000, 500_000, -200_000)
        assert audited == 12_300_000
        # 回写payload验证
        payload = {
            "account_code": "1811",
            "audited_amount": audited,
            "direction": "debit",
        }
        assert payload["account_code"] == "1811"
        assert payload["direction"] == "debit"
        assert payload["audited_amount"] == 12_300_000


# ═══════════════════════════════════════════════════════════════════════════════
# Section 8: E2E 完整流程（纯函数闭环）
# ═══════════════════════════════════════════════════════════════════════════════


class TestE2EFlow:
    """完整流程：TB取数→审定→明细→测算→亏损→N3→N5"""

    def test_full_pipeline(self):
        """N1完整计算流程闭环"""
        from app.services.n1_deferred_tax_assets_service import (
            calc_asset_end_balance,
            calc_audited_amount,
            calc_temporary_difference,
            calc_deferred_tax_asset,
            calc_unrecovered_loss,
            calc_recognizable_asset,
            classify_temporary_differences,
        )

        # Step 1: TB取数（资产类借方）
        begin = 10_000_000
        debit = 5_000_000
        credit = 2_000_000
        end_balance = calc_asset_end_balance(begin, debit, credit)
        assert end_balance == 13_000_000

        # Step 2: 审定数
        audited = calc_audited_amount(end_balance, 200_000, -100_000)
        assert audited == 13_100_000

        # Step 3: 暂时性差异分类
        rows = [
            {"bookValue": 5_000_000, "taxBase": 8_000_000},   # 可抵扣300万
            {"bookValue": 2_000_000, "taxBase": 4_000_000},   # 可抵扣200万
            {"bookValue": 10_000_000, "taxBase": 7_000_000},  # 应纳税300万→N3
        ]
        classified = classify_temporary_differences(rows)
        assert len(classified["deductible"]) == 2
        assert len(classified["taxable"]) == 1

        # Step 4: 递延税资产合计
        total_deductible = sum(
            r["deductibleDiff"] for r in classified["deductible"]
        )
        assert total_deductible == 5_000_000  # 300万+200万
        dta = calc_deferred_tax_asset(total_deductible, 0.25)
        assert dta == 1_250_000

        # Step 5: 可弥补亏损确认
        unrecovered = calc_unrecovered_loss(4_000_000, 1_000_000)
        assert unrecovered == 3_000_000
        loss_asset = calc_recognizable_asset(unrecovered, 2_000_000, 0.25)
        assert loss_asset == 500_000  # min(300,200)×25%

        # Step 6: 跨底稿
        total_asset = dta + loss_asset  # 125万+50万=175万
        assert total_asset == 1_750_000
        total_liability = calc_deferred_tax_asset(
            classified["taxable"][0]["taxableDiff"], 0.25
        )
        assert total_liability == 750_000

        # Step 7: N5递延税费用核对
        period_change = end_balance - begin  # 300万
        assert period_change == 3_000_000
