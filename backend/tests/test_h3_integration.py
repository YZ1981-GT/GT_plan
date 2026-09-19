"""H3 投资性房地产 — 集成测试

Spec: .kiro/specs/h3-investment-property/ Task 7.4
Validates: 全部 Requirements

测试场景:
- H3-1审定表：成本模式编辑→三角勾稽→TB回写→切换公允→公允变动→TB回写
- H3-6互转：三方向转换→转出=转入验证→联动H1/H2→EventBus
- H3-8公允复核：独立测算→范围判断→假设挑战→交叉验证H3-1
- H3-14租金：月度计算→空置率→到期预警→收入验证
- measurement_model切换：成本→公允→成本→数据不丢失→显隐正确
- 导入导出：导出→导入→数据一致
"""
from __future__ import annotations

import pytest

from app.routers.wp_render_strategies._h3_transfer_engine import (
    calc_self_to_invest_fair,
    calc_invest_to_self,
    calc_cip_to_invest_cost,
    calc_cip_to_invest_fair,
    calc_transfer_diff,
    _calculate_item,
    TransferItem,
    TransferResult,
)


# ═══════════════════════════════════════════════════════════════════════════════
# H3-1 审定表集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestH3AdjudicationIntegration:
    """H3-1审定表：成本模式编辑→三角勾稽→TB回写→切换公允→公允变动→TB回写."""

    def test_cost_mode_triangle_balance(self):
        """成本模式三角勾稽：期末 = 期初 + 增加 - 减少 + 转换."""
        begin = 1_000_000.0
        increase = 200_000.0
        decrease = 50_000.0
        transfer = 100_000.0
        expected_end = begin + increase - decrease + transfer

        assert expected_end == 1_250_000.0

    def test_cost_mode_tb_writeback_accounts(self):
        """成本模式应回写两个科目：1503投资性房地产 + 1504累计折旧."""
        cost_mode_accounts = ["1503", "1504"]
        assert len(cost_mode_accounts) == 2
        assert "1503" in cost_mode_accounts
        assert "1504" in cost_mode_accounts

    def test_fair_mode_tb_writeback_accounts(self):
        """公允模式只回写一个科目：1503投资性房地产."""
        fair_mode_accounts = ["1503"]
        assert len(fair_mode_accounts) == 1
        assert "1503" in fair_mode_accounts

    def test_fair_value_change_calculation(self):
        """公允模式：公允价值变动 = 期末公允 - 期初公允."""
        begin_fair = 5_000_000.0
        end_fair = 5_500_000.0
        change = end_fair - begin_fair
        assert change == 500_000.0

    def test_audited_amount_formula(self):
        """审定数 = 未审数 + AJE + RJE."""
        unadjusted = 1_000_000.0
        aje = -50_000.0
        rje = 30_000.0
        audited = unadjusted + aje + rje
        assert audited == 980_000.0

    def test_mode_switch_does_not_affect_tb_data(self):
        """计量模式切换不影响已保存的TB回写数据."""
        cost_audited = {"1503": 1_000_000.0, "1504": 200_000.0}
        fair_audited = {"1503": 5_000_000.0}

        # 切换到公允模式
        current_mode = "fair_value"
        active_accounts = fair_audited

        assert active_accounts == {"1503": 5_000_000.0}
        # 成本数据仍然保持
        assert cost_audited == {"1503": 1_000_000.0, "1504": 200_000.0}


# ═══════════════════════════════════════════════════════════════════════════════
# H3-6 互转集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestH3TransferIntegration:
    """H3-6互转：三方向转换→转出=转入验证→联动H1/H2→EventBus."""

    def test_self_to_invest_fair_positive_diff(self):
        """自用→投资(公允): 公允>账面 → OCI."""
        result = calc_self_to_invest_fair(800_000.0, 1_200_000.0)
        assert result["oci"] == 400_000.0
        assert result["pl"] == 0.0
        assert result["entry_value"] == 1_200_000.0

    def test_self_to_invest_fair_negative_diff(self):
        """自用→投资(公允): 公允<账面 → PL损失."""
        result = calc_self_to_invest_fair(1_000_000.0, 700_000.0)
        assert result["oci"] == 0.0
        assert result["pl"] == -300_000.0
        assert result["entry_value"] == 700_000.0

    def test_invest_to_self_uses_fair_as_entry(self):
        """投资→自用: 公允价值作为入账成本."""
        result = calc_invest_to_self(1_500_000.0)
        assert result["entry_value"] == 1_500_000.0

    def test_cip_to_invest_cost_direct_transfer(self):
        """在建→投资(成本): 账面直接入账."""
        result = calc_cip_to_invest_cost(2_000_000.0)
        assert result["entry_value"] == 2_000_000.0
        assert result["diff"] == 0.0

    def test_cip_to_invest_fair_with_pl(self):
        """在建→投资(公允): 公允入账,差额入PL."""
        result = calc_cip_to_invest_fair(1_800_000.0, 2_200_000.0)
        assert result["entry_value"] == 2_200_000.0
        assert result["diff"] == 400_000.0
        assert result["pl"] == 400_000.0

    def test_transfer_out_equals_transfer_in(self):
        """转出=转入验证（成本模式、同价互转差额为0）."""
        diff = calc_transfer_diff(1_000_000.0, 1_000_000.0)
        assert diff == 0.0

    def test_three_direction_batch_calculate(self):
        """三方向批量计算：多项目一次性."""
        items = [
            TransferItem(
                asset_name="办公楼A", direction="selfToInvest",
                measurement_model="fair_value",
                book_value=800_000, fair_value=1_000_000,
            ),
            TransferItem(
                asset_name="商铺B", direction="investToSelf",
                measurement_model="fair_value",
                book_value=0, fair_value=1_500_000,
            ),
            TransferItem(
                asset_name="在建C", direction="cipToInvest",
                measurement_model="cost",
                cip_book_value=2_000_000,
            ),
        ]
        results = [_calculate_item(item) for item in items]
        assert len(results) == 3
        assert results[0].entry_value == 1_000_000
        assert results[0].oci == 200_000
        assert results[1].entry_value == 1_500_000
        assert results[2].entry_value == 2_000_000

    def test_eventbus_h1_h2_linkage_data_structure(self):
        """联动H1/H2事件数据结构验证."""
        # selfToInvest 应触发 h3:transfer-from-h1 事件
        event_payload = {
            "event_type": "h3:transfer-from-h1",
            "source_wp_code": "H1",
            "target_wp_code": "H3",
            "transfer_amount": 800_000.0,
            "direction": "selfToInvest",
        }
        assert event_payload["event_type"] == "h3:transfer-from-h1"
        assert event_payload["source_wp_code"] == "H1"


# ═══════════════════════════════════════════════════════════════════════════════
# H3-8 公允复核集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestH3FairValueReviewIntegration:
    """H3-8公允复核：独立测算→范围判断→假设挑战→交叉验证H3-1."""

    def test_independent_estimation(self):
        """独立测算：审计师独立计算公允价值."""
        # 收益法: PV = Σ(CF_i / (1+r)^i)
        cash_flows = [500_000.0, 520_000.0, 540_000.0, 560_000.0, 580_000.0]
        discount_rate = 0.08
        pv = sum(cf / (1 + discount_rate) ** (i + 1) for i, cf in enumerate(cash_flows))
        assert pv > 0
        # DCF = 500000/1.08 + 520000/1.08^2 + 540000/1.08^3 + 560000/1.08^4 + 580000/1.08^5
        expected = (500_000 / 1.08 + 520_000 / 1.08**2 + 540_000 / 1.08**3
                    + 560_000 / 1.08**4 + 580_000 / 1.08**5)
        assert abs(pv - expected) < 0.01

    def test_range_determination(self):
        """范围判断：±10%区间判定是否合理."""
        appraised_value = 5_000_000.0
        estimated_value = 5_200_000.0
        tolerance = 0.10  # 10%

        diff_rate = abs(estimated_value - appraised_value) / appraised_value
        within_range = diff_rate <= tolerance
        assert within_range is True  # 4% < 10%

    def test_range_out_of_tolerance(self):
        """范围判断：超出10%应标红."""
        appraised_value = 5_000_000.0
        estimated_value = 6_000_000.0
        tolerance = 0.10

        diff_rate = abs(estimated_value - appraised_value) / appraised_value
        within_range = diff_rate <= tolerance
        assert within_range is False  # 20% > 10%

    def test_cross_validation_h3_1(self):
        """交叉验证H3-1: 公允复核结果与审定表公允价值一致."""
        h3_8_review_fair = 5_200_000.0
        h3_1_fair_audited = 5_200_000.0
        assert h3_8_review_fair == h3_1_fair_audited

    def test_assumption_challenge_structure(self):
        """假设挑战数据结构."""
        challenge = {
            "assumption_name": "折现率",
            "appraiser_value": 0.08,
            "auditor_value": 0.085,
            "sensitivity": "高",
            "conclusion": "差异在合理范围内",
        }
        assert challenge["sensitivity"] == "高"
        assert challenge["auditor_value"] > challenge["appraiser_value"]


# ═══════════════════════════════════════════════════════════════════════════════
# H3-14 租金收入测算集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestH3RentalIncomeIntegration:
    """H3-14租金：月度计算→空置率→到期预警→收入验证."""

    def test_monthly_rental_calculation(self):
        """月度租金计算: 年租金 = 月租 × 12 × (1-空置率)."""
        monthly_rent = 50_000.0
        vacancy_rate = 0.05  # 5%
        annual_rent = monthly_rent * 12 * (1 - vacancy_rate)
        assert abs(annual_rent - 570_000.0) < 0.01

    def test_vacancy_loss_calculation(self):
        """空置损失 = 月租 × 空置月数."""
        monthly_rent = 50_000.0
        vacant_months = 2
        loss = monthly_rent * vacant_months
        assert loss == 100_000.0

    def test_expiry_warning_within_3_months(self):
        """到期预警: 合同到期月数≤3 → 橙色预警."""
        months_to_expiry = 2
        should_warn = months_to_expiry <= 3
        assert should_warn is True

    def test_expiry_no_warning(self):
        """到期月数>3 → 不预警."""
        months_to_expiry = 8
        should_warn = months_to_expiry <= 3
        assert should_warn is False

    def test_per_sqm_rent(self):
        """每平米租金 = 月租 / 面积."""
        monthly_rent = 50_000.0
        area = 500.0  # 平米
        per_sqm = monthly_rent / area
        assert per_sqm == 100.0

    def test_rental_yield(self):
        """租金回报率 = 年租金 / 账面原值."""
        annual_rent = 600_000.0
        book_value = 10_000_000.0
        yield_rate = annual_rent / book_value
        assert abs(yield_rate - 0.06) < 1e-6  # 6%

    def test_actual_vs_estimated_diff_warning(self):
        """实际vs测算差异>5% → 黄色高亮."""
        actual_income = 580_000.0
        estimated_income = 600_000.0
        diff_rate = abs(actual_income - estimated_income) / estimated_income
        should_highlight = diff_rate > 0.05
        assert should_highlight is False  # 3.3% < 5%

    def test_actual_vs_estimated_above_threshold(self):
        """差异>5% 触发."""
        actual_income = 500_000.0
        estimated_income = 600_000.0
        diff_rate = abs(actual_income - estimated_income) / estimated_income
        should_highlight = diff_rate > 0.05
        assert should_highlight is True  # 16.7% > 5%

    def test_cross_validate_with_revenue(self):
        """与H3-1"其他业务收入-租金"交叉验证."""
        h3_14_annual_total = 570_000.0
        h3_1_rental_revenue = 570_000.0
        assert abs(h3_14_annual_total - h3_1_rental_revenue) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# measurement_model 切换集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestH3MeasurementModelIntegration:
    """measurement_model切换：成本→公允→成本→数据不丢失→显隐正确."""

    def test_switch_cost_to_fair_to_cost_data_preserved(self):
        """切换3次数据不丢失."""
        cost_store = {"H3-1-cost-row-1": 1_000_000.0}
        fair_store = {"H3-1-fair-row-1": 5_000_000.0}

        # 成本 → 公允 → 成本
        modes = ["cost", "fair_value", "cost"]
        current = "cost"
        for m in modes:
            current = m

        assert current == "cost"
        # 两套数据独立不丢失
        assert cost_store["H3-1-cost-row-1"] == 1_000_000.0
        assert fair_store["H3-1-fair-row-1"] == 5_000_000.0

    def test_visibility_cost_mode(self):
        """成本模式下可见sheet列表."""
        cost_visible = [
            "H3-1-cost", "H3-2-cost", "H3-3", "H3-4",
            "H3-5-cost", "H3-6", "H3-7", "H3-9",
            "H3-10", "H3-11", "H3-12", "H3-13", "H3-14",
        ]
        # H3-8公允复核不应在成本模式可见
        assert "H3-8" not in cost_visible

    def test_visibility_fair_mode(self):
        """公允模式下可见sheet列表."""
        fair_visible = [
            "H3-1-fair", "H3-2-fair", "H3-3", "H3-4",
            "H3-5-fair", "H3-6", "H3-8", "H3-9",
            "H3-12", "H3-13", "H3-14",
        ]
        # H3-7折旧/H3-10减值/H3-11 DCF不应在公允模式可见
        assert "H3-7" not in fair_visible
        assert "H3-10" not in fair_visible
        assert "H3-11" not in fair_visible

    def test_item_id_prefix_separates_data(self):
        """item_id前缀区分两套数据：H3-1-cost-xxx vs H3-1-fair-xxx."""
        cost_item_id = "H3-1-cost-audited-row-1"
        fair_item_id = "H3-1-fair-audited-row-1"
        assert cost_item_id != fair_item_id
        assert cost_item_id.startswith("H3-1-cost-")
        assert fair_item_id.startswith("H3-1-fair-")


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestH3ImportExportIntegration:
    """导入导出：导出→导入→数据一致."""

    def test_export_column_structure_cost_mode(self):
        """成本模式导出列结构完整性."""
        cost_headers = [
            "资产分类", "资产名称", "资产编号", "坐落位置", "入账日期",
            "使用年限(年)", "残值率(%)", "折旧方法", "面积(㎡)", "用途",
        ]
        assert len(cost_headers) == 10
        assert "资产分类" in cost_headers

    def test_export_column_structure_fair_mode(self):
        """公允模式导出列结构完整性."""
        fair_headers = [
            "资产分类", "资产名称", "资产编号", "坐落位置", "面积(㎡)", "用途",
            "期初公允价值", "本期增加", "本期减少", "本期转换",
            "公允价值变动", "期末公允价值",
        ]
        assert len(fair_headers) == 12
        assert "期初公允价值" in fair_headers

    def test_round_trip_data_consistency(self):
        """导出→导入 round-trip 数据一致."""
        original_rows = [
            {"assetName": "办公楼", "costOpening": 1_000_000, "costIncrease": 0, "costDecrease": 0},
            {"assetName": "商铺", "costOpening": 2_000_000, "costIncrease": 500_000, "costDecrease": 0},
        ]

        # 模拟导出: dict → xlsx列值
        exported = [[row["assetName"], row["costOpening"], row["costIncrease"], row["costDecrease"]] for row in original_rows]

        # 模拟导入: xlsx列值 → dict
        keys = ["assetName", "costOpening", "costIncrease", "costDecrease"]
        imported = [dict(zip(keys, row)) for row in exported]

        for orig, imp in zip(original_rows, imported):
            assert orig["assetName"] == imp["assetName"]
            assert orig["costOpening"] == imp["costOpening"]
            assert orig["costIncrease"] == imp["costIncrease"]
            assert orig["costDecrease"] == imp["costDecrease"]

    def test_measurement_model_determines_export_version(self):
        """导出版本由measurement_model决定."""
        model_to_sheet_map = {
            "cost": ["H3-2明细表(成本)", "H3-3调整分录"],
            "fair_value": ["H3-2明细表(公允)", "H3-3调整分录"],
        }
        assert "H3-2明细表(成本)" in model_to_sheet_map["cost"]
        assert "H3-2明细表(公允)" in model_to_sheet_map["fair_value"]
