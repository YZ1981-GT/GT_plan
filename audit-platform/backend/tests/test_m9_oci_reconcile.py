"""M9 其他综合收益 — OCI核对集成测试 (Task 7.2).

覆盖：
1. calc_reconcile_diff 纯函数
2. aggregate_oci 纯函数
3. run_oci_reconciliation 多来源核对
4. validate_equity_formula 权益类公式校验

Spec: .kiro/specs/m9-other-comprehensive-income/ Task 7.2
Requirements: 4.1-4.8

科目：4103 其他综合收益（**贷方/权益类！期末=期初+贷方-借方**）
OCI汇聚多来源：G8公允变动/J2重计量/其他债权投资/套期/外币折算
分两大类：不能重分类进损益 + 能重分类进损益
"""

from __future__ import annotations

import pytest

from app.services.m9_other_comprehensive_income_service import (
    calc_after_tax_net,
    calc_reconcile_diff,
    aggregate_oci,
    run_oci_reconciliation,
    validate_equity_formula,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1: calc_reconcile_diff — 核对差异纯函数 (Req 4.5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcReconcileDiff:
    """核对差异 = 来源金额 - 账面OCI增加"""

    def test_zero_diff_when_equal(self):
        """来源=账面 → 差异=0"""
        assert calc_reconcile_diff(750000, 750000) == 0.0

    def test_positive_diff_source_greater(self):
        """来源>账面 → 正差（OCI可能漏记）"""
        result = calc_reconcile_diff(1000000, 800000)
        assert result == 200000.0

    def test_negative_diff_booked_greater(self):
        """来源<账面 → 负差（OCI可能多记）"""
        result = calc_reconcile_diff(300000, 450000)
        assert result == -150000.0

    def test_zero_inputs(self):
        """两侧均为0"""
        assert calc_reconcile_diff(0, 0) == 0.0

    def test_none_handling(self):
        """None → 视为0"""
        assert calc_reconcile_diff(None, 500000) == -500000.0  # type: ignore[arg-type]
        assert calc_reconcile_diff(500000, None) == 500000.0  # type: ignore[arg-type]

    def test_negative_values(self):
        """负值情况（OCI减少/重分类场景）"""
        # 来源-100万，账面-80万 → 差-20万
        result = calc_reconcile_diff(-1000000, -800000)
        assert result == -200000.0

    def test_g8_fair_value_scenario(self):
        """G8场景：其他权益工具投资公允变动 → 来源=G8税后净额"""
        g8_after_tax = 750000  # G8税后净额
        m9_booked = 750000     # M9-4核对表账面
        assert calc_reconcile_diff(g8_after_tax, m9_booked) == 0.0

    def test_j2_remeasured_scenario(self):
        """J2场景：设定受益计划重计量 → 来源=J2税后净额"""
        j2_after_tax = 450000  # J2税后净额
        m9_booked = 430000     # M9-4核对表账面（有差异20000）
        assert calc_reconcile_diff(j2_after_tax, m9_booked) == 20000.0


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: aggregate_oci — OCI两大类汇总 (Req 6.3)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAggregateOci:
    """OCI两大类汇总：不可重分类 + 可重分类 = 合计"""

    def test_both_categories(self):
        """两大类都有值"""
        items = [
            {"category": "non_reclass", "amount": 750000},   # G8公允变动
            {"category": "non_reclass", "amount": 450000},   # J2重计量
            {"category": "reclass", "amount": 300000},       # 其他债权投资
            {"category": "reclass", "amount": 200000},       # 外币折算
        ]
        result = aggregate_oci(items)
        assert result["non_reclass"] == 1200000.0
        assert result["reclass"] == 500000.0
        assert result["total"] == 1700000.0
        # P5: total = non_reclass + reclass
        assert result["total"] == result["non_reclass"] + result["reclass"]

    def test_only_non_reclass(self):
        """仅不可重分类（G8+J2）"""
        items = [
            {"category": "non_reclass", "amount": 500000},
            {"category": "non_reclass", "amount": 300000},
        ]
        result = aggregate_oci(items)
        assert result["non_reclass"] == 800000.0
        assert result["reclass"] == 0.0
        assert result["total"] == 800000.0

    def test_only_reclass(self):
        """仅可重分类（其他债权+套期+外币）"""
        items = [
            {"category": "reclass", "amount": 100000},
            {"category": "reclass", "amount": 200000},
            {"category": "reclass", "amount": 150000},
        ]
        result = aggregate_oci(items)
        assert result["non_reclass"] == 0.0
        assert result["reclass"] == 450000.0
        assert result["total"] == 450000.0

    def test_empty_items(self):
        """空列表"""
        result = aggregate_oci([])
        assert result["non_reclass"] == 0.0
        assert result["reclass"] == 0.0
        assert result["total"] == 0.0

    def test_invalid_category_ignored(self):
        """无效分类被忽略"""
        items = [
            {"category": "non_reclass", "amount": 100},
            {"category": "invalid", "amount": 999},
            {"category": "reclass", "amount": 200},
        ]
        result = aggregate_oci(items)
        assert result["non_reclass"] == 100.0
        assert result["reclass"] == 200.0
        assert result["total"] == 300.0

    def test_none_amount_treated_as_zero(self):
        """amount为None视为0"""
        items = [
            {"category": "non_reclass", "amount": None},
            {"category": "reclass", "amount": 500},
        ]
        result = aggregate_oci(items)
        assert result["non_reclass"] == 0.0
        assert result["reclass"] == 500.0


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3: run_oci_reconciliation — 多来源核对 (Req 4.1-4.6)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunOciReconciliation:
    """完整OCI多来源核对执行"""

    def test_all_consistent_no_threshold(self):
        """所有来源一致（无阈值）"""
        sources = [
            {"code": "G8", "name": "其他权益工具投资公允变动", "source_amount": 750000, "booked_amount": 750000},
            {"code": "J2", "name": "设定受益计划重计量", "source_amount": 450000, "booked_amount": 450000},
        ]
        result = run_oci_reconciliation(sources, threshold=0)
        assert result["all_consistent"] is True
        assert result["inconsistent_count"] == 0
        assert result["total_diff"] == 0.0
        assert result["total_source"] == 1200000.0
        assert result["total_booked"] == 1200000.0
        assert len(result["items"]) == 2

    def test_with_threshold_exceed(self):
        """有来源超过阈值"""
        sources = [
            {"code": "G8", "name": "G8公允变动", "source_amount": 750000, "booked_amount": 750000},
            {"code": "J2", "name": "J2重计量", "source_amount": 450000, "booked_amount": 400000},
            {"code": "FX", "name": "外币折算", "source_amount": 300000, "booked_amount": 280000},
        ]
        result = run_oci_reconciliation(sources, threshold=10000)

        assert result["all_consistent"] is False
        assert result["inconsistent_count"] == 2  # J2差50000 + FX差20000

        # 验证各行差异
        g8_item = next(i for i in result["items"] if i["code"] == "G8")
        assert g8_item["diff"] == 0.0
        assert g8_item["exceed_threshold"] is False

        j2_item = next(i for i in result["items"] if i["code"] == "J2")
        assert j2_item["diff"] == 50000.0
        assert j2_item["exceed_threshold"] is True

        fx_item = next(i for i in result["items"] if i["code"] == "FX")
        assert fx_item["diff"] == 20000.0
        assert fx_item["exceed_threshold"] is True

    def test_total_calculations(self):
        """汇总计算正确"""
        sources = [
            {"code": "G8", "name": "G8", "source_amount": 1000000, "booked_amount": 900000},
            {"code": "J2", "name": "J2", "source_amount": 500000, "booked_amount": 480000},
            {"code": "FX", "name": "FX", "source_amount": 200000, "booked_amount": 200000},
        ]
        result = run_oci_reconciliation(sources, threshold=0)

        assert result["total_source"] == 1700000.0
        assert result["total_booked"] == 1580000.0
        assert result["total_diff"] == 120000.0  # 1700000-1580000

    def test_empty_sources(self):
        """空来源列表"""
        result = run_oci_reconciliation([], threshold=0)
        assert result["all_consistent"] is True
        assert result["inconsistent_count"] == 0
        assert result["total_source"] == 0.0
        assert result["total_booked"] == 0.0
        assert result["total_diff"] == 0.0
        assert result["items"] == []

    def test_none_amounts_handled(self):
        """None金额视为0"""
        sources = [
            {"code": "G8", "name": "G8", "source_amount": None, "booked_amount": 500000},
        ]
        result = run_oci_reconciliation(sources, threshold=0)
        assert result["items"][0]["diff"] == -500000.0

    def test_full_five_source_reconciliation(self):
        """完整5来源核对（G8+J2+其他债权+套期+外币）"""
        sources = [
            {"code": "G8", "name": "其他权益工具投资公允价值变动", "source_amount": 750000, "booked_amount": 750000},
            {"code": "J2", "name": "设定受益计划重计量", "source_amount": 450000, "booked_amount": 450000},
            {"code": "DEBT-FV", "name": "其他债权投资公允变动", "source_amount": 300000, "booked_amount": 300000},
            {"code": "HEDGE", "name": "现金流量套期损益", "source_amount": 120000, "booked_amount": 120000},
            {"code": "FX", "name": "外币财务报表折算差额", "source_amount": 80000, "booked_amount": 80000},
        ]
        result = run_oci_reconciliation(sources, threshold=100)

        assert result["all_consistent"] is True
        assert result["total_source"] == 1700000.0
        assert result["total_booked"] == 1700000.0
        assert result["total_diff"] == 0.0
        assert len(result["items"]) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4: validate_equity_formula — 权益类公式校验 (Req 6.4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateEquityFormula:
    """权益类公式校验：期末 = 期初 + 贷方 - 借方"""

    def test_correct_formula(self):
        """期末=期初+贷方-借方 正确"""
        # 1000 + 300 - 100 = 1200
        assert validate_equity_formula(1000, 300, 100, 1200) is True

    def test_incorrect_formula(self):
        """公式不成立"""
        # 1000 + 300 - 100 = 1200 ≠ 1300
        assert validate_equity_formula(1000, 300, 100, 1300) is False

    def test_tolerance_within_threshold(self):
        """容差0.01元内视为一致"""
        # 1000 + 300 - 100 = 1200, 期末=1200.005 → 差<0.01
        assert validate_equity_formula(1000, 300, 100, 1200.005) is True

    def test_tolerance_exceed_threshold(self):
        """超过容差0.01"""
        # 差=0.02 > 0.01
        assert validate_equity_formula(1000, 300, 100, 1200.02) is False

    def test_zero_all(self):
        """全0 → 成立"""
        assert validate_equity_formula(0, 0, 0, 0) is True

    def test_none_handling(self):
        """None → 视为0"""
        # 0 + 0 - 0 = 0
        assert validate_equity_formula(None, None, None, 0) is True  # type: ignore[arg-type]

    def test_oci_increase_scenario(self):
        """OCI增加场景：期初5M + 贷方(增加)2M - 借方(重分类)0.5M = 期末6.5M"""
        assert validate_equity_formula(5000000, 2000000, 500000, 6500000) is True

    def test_oci_decrease_scenario(self):
        """OCI减少场景：处置时重分类进损益"""
        # 期初3M + 贷方0 - 借方1M(处置重分类) = 期末2M
        assert validate_equity_formula(3000000, 0, 1000000, 2000000) is True

    def test_large_numbers(self):
        """大额数字精度"""
        begin = 100_000_000.0
        credit = 50_000_000.0
        debit = 20_000_000.0
        end = 130_000_000.0  # 100M + 50M - 20M
        assert validate_equity_formula(begin, credit, debit, end) is True


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5: calc_after_tax_net — 税后净额 (Req 6.1)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalcAfterTaxNet:
    """OCI税后净额 = 税前发生 - 所得税影响"""

    def test_basic_calculation(self):
        """基础计算"""
        assert calc_after_tax_net(1000000, 250000) == 750000.0

    def test_zero_tax_effect(self):
        """无税额影响"""
        assert calc_after_tax_net(500000, 0) == 500000.0

    def test_none_inputs(self):
        """None → 0"""
        assert calc_after_tax_net(None, 200000) == -200000.0  # type: ignore[arg-type]
        assert calc_after_tax_net(300000, None) == 300000.0  # type: ignore[arg-type]

    def test_negative_pre_tax(self):
        """负税前（OCI减少/损失）"""
        # 公允价值下降-100万，税额影响-25万 → 税后-75万
        assert calc_after_tax_net(-1000000, -250000) == -750000.0


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6: E2E — 完整核对流程 G8+J2→OCI核对 (Req 4.1-4.8)
# ═══════════════════════════════════════════════════════════════════════════════


class TestOciReconciliationE2E:
    """完整核对流程闭环"""

    def test_g8_j2_to_oci_reconciliation_flow(self):
        """G8税后净额+J2税后净额 → run_oci_reconciliation → 一致"""
        # G8: 税前100万，税额25万 → 税后75万
        g8_after_tax = calc_after_tax_net(1000000, 250000)
        assert g8_after_tax == 750000.0

        # J2: 税前60万，税额15万 → 税后45万
        j2_after_tax = calc_after_tax_net(600000, 150000)
        assert j2_after_tax == 450000.0

        # 假设账面已正确入账
        sources = [
            {"code": "G8", "name": "G8公允变动", "source_amount": g8_after_tax, "booked_amount": g8_after_tax},
            {"code": "J2", "name": "J2重计量", "source_amount": j2_after_tax, "booked_amount": j2_after_tax},
        ]
        result = run_oci_reconciliation(sources, threshold=100)
        assert result["all_consistent"] is True
        assert result["total_diff"] == 0.0

        # 验证权益类公式：期初2M + 贷方(G8+J2=120万) - 借方0 = 期末3.2M
        begin = 2000000
        credit = g8_after_tax + j2_after_tax  # 750000+450000=1200000
        debit = 0
        end = begin + credit - debit  # 3200000
        assert validate_equity_formula(begin, credit, debit, end) is True

    def test_with_discrepancy_and_threshold(self):
        """有差异的核对场景 + 阈值判断"""
        # G8少入账5万
        g8_source = calc_after_tax_net(1000000, 250000)  # 75万
        g8_booked = 700000  # 实际入账70万，少5万

        # J2多入账2万
        j2_source = calc_after_tax_net(600000, 150000)  # 45万
        j2_booked = 470000  # 实际入账47万，多2万

        sources = [
            {"code": "G8", "name": "G8公允变动", "source_amount": g8_source, "booked_amount": g8_booked},
            {"code": "J2", "name": "J2重计量", "source_amount": j2_source, "booked_amount": j2_booked},
        ]

        # 阈值3万：G8差5万>3万超标，J2差-2万<3万不超
        result = run_oci_reconciliation(sources, threshold=30000)
        assert result["all_consistent"] is False
        assert result["inconsistent_count"] == 1

        g8_item = next(i for i in result["items"] if i["code"] == "G8")
        assert g8_item["diff"] == 50000.0
        assert g8_item["exceed_threshold"] is True

        j2_item = next(i for i in result["items"] if i["code"] == "J2")
        assert j2_item["diff"] == -20000.0
        assert j2_item["exceed_threshold"] is False

    def test_aggregate_oci_matches_reconciliation_totals(self):
        """aggregate_oci 与 run_oci_reconciliation 总额一致"""
        # 模拟5个来源
        items_for_aggregate = [
            {"category": "non_reclass", "amount": 750000},   # G8
            {"category": "non_reclass", "amount": 450000},   # J2
            {"category": "reclass", "amount": 300000},       # 其他债权
            {"category": "reclass", "amount": 120000},       # 套期
            {"category": "reclass", "amount": 80000},        # 外币
        ]
        agg = aggregate_oci(items_for_aggregate)

        sources_for_reconcile = [
            {"code": "G8", "name": "G8", "source_amount": 750000, "booked_amount": 750000},
            {"code": "J2", "name": "J2", "source_amount": 450000, "booked_amount": 450000},
            {"code": "DEBT", "name": "其他债权", "source_amount": 300000, "booked_amount": 300000},
            {"code": "HEDGE", "name": "套期", "source_amount": 120000, "booked_amount": 120000},
            {"code": "FX", "name": "外币", "source_amount": 80000, "booked_amount": 80000},
        ]
        recon = run_oci_reconciliation(sources_for_reconcile, threshold=0)

        # aggregate total = reconciliation total_source
        assert agg["total"] == recon["total_source"]
        assert agg["total"] == 1700000.0
