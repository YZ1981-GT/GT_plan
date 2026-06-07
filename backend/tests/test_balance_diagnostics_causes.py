"""诊断原因排序与解释测试。

覆盖:
- 3.1 report_line_unmatched 原因
- 3.2 sign_convention_anomaly 原因
- 3.3 pnl_not_closed_or_caliber_gap 原因
- 3.4 source_data_unbalanced 原因
- 3.5 manual_review_required 原因
- 3.6 top_contributors 四种结构
- 3.7 原因按 severity 和 confidence 排序
"""

import pytest

from backend.app.services.balance_diagnostics.cause_builders import (
    build_balance_sheet_equation_contributors,
    build_balance_vs_ledger_contributors,
    build_ledger_debit_credit_contributors,
    build_manual_review_required_cause,
    build_pnl_not_closed_cause,
    build_report_line_unmatched_cause,
    build_sign_convention_anomaly_cause,
    build_source_data_unbalanced_cause,
    build_trial_balance_debit_credit_contributors,
    sort_causes,
)
from backend.app.services.balance_diagnostics.diagnostics_types import DiagnosticCause


# ---------------------------------------------------------------------------
# 3.1 report_line_unmatched
# ---------------------------------------------------------------------------


class TestReportLineUnmatchedCause:
    """report_line_unmatched 原因构建。"""

    def test_basic_construction(self):
        cause = build_report_line_unmatched_cause(
            unmatched_count=5,
            total_unmatched_amount=150000.0,
            sample_accounts=["2701", "4003", "2922"],
        )
        assert cause.cause_code == "report_line_unmatched"
        assert cause.severity == 3
        assert 0.0 <= cause.confidence <= 1.0
        assert "5 个" in cause.description
        assert "150,000.00" in cause.description
        assert cause.evidence["unmatched_count"] == 5

    def test_confidence_increases_with_count(self):
        cause_low = build_report_line_unmatched_cause(unmatched_count=1)
        cause_high = build_report_line_unmatched_cause(unmatched_count=10)
        assert cause_high.confidence > cause_low.confidence

    def test_confidence_capped_at_0_9(self):
        cause = build_report_line_unmatched_cause(unmatched_count=100)
        assert cause.confidence <= 0.9


# ---------------------------------------------------------------------------
# 3.2 sign_convention_anomaly
# ---------------------------------------------------------------------------


class TestSignConventionAnomalyCause:
    """sign_convention_anomaly 原因构建。"""

    def test_basic_construction(self):
        cause = build_sign_convention_anomaly_cause(
            anomaly_count=3,
            sample_anomalies=[{"account_code": "2221", "reason": "贷方正常余额存负数"}],
        )
        assert cause.cause_code == "sign_convention_anomaly"
        assert cause.severity == 4
        assert "3 个" in cause.description
        assert cause.evidence["anomaly_count"] == 3

    def test_severity_is_4(self):
        cause = build_sign_convention_anomaly_cause(anomaly_count=1)
        assert cause.severity == 4


# ---------------------------------------------------------------------------
# 3.3 pnl_not_closed_or_caliber_gap
# ---------------------------------------------------------------------------


class TestPnlNotClosedCause:
    """pnl_not_closed_or_caliber_gap 原因构建。"""

    def test_pnl_not_closed(self):
        cause = build_pnl_not_closed_cause(pnl_balance=500000.0)
        assert cause.cause_code == "pnl_not_closed_or_caliber_gap"
        assert cause.severity == 4
        assert "500,000.00" in cause.description
        assert "资产=负债+权益" in cause.description or "试算平衡" in cause.description

    def test_caliber_mismatch(self):
        cause = build_pnl_not_closed_cause(caliber_mismatch=True)
        assert "口径" in cause.description
        assert cause.evidence["caliber_mismatch"] is True


# ---------------------------------------------------------------------------
# 3.4 source_data_unbalanced
# ---------------------------------------------------------------------------


class TestSourceDataUnbalancedCause:
    """source_data_unbalanced 原因构建。"""

    def test_basic_construction(self):
        cause = build_source_data_unbalanced_cause(
            difference=44030236.47,
            caliber="ledger_debit_credit",
            top_vouchers=["V001", "V002"],
        )
        assert cause.cause_code == "source_data_unbalanced"
        assert cause.severity == 5
        assert cause.confidence == 0.95
        assert "44,030,236.47" in cause.description
        assert cause.evidence["top_vouchers"] == ["V001", "V002"]


# ---------------------------------------------------------------------------
# 3.5 manual_review_required
# ---------------------------------------------------------------------------


class TestManualReviewRequiredCause:
    """manual_review_required 原因构建。"""

    def test_basic_construction(self):
        cause = build_manual_review_required_cause("多个口径均有差异")
        assert cause.cause_code == "manual_review_required"
        assert cause.severity == 2
        assert cause.confidence == 0.0
        assert "人工复核" in cause.description


# ---------------------------------------------------------------------------
# 3.6 top_contributors 四种结构
# ---------------------------------------------------------------------------


class TestTopContributors:
    """四种 caliber 的 top_contributors 结构。"""

    def test_ledger_debit_credit_contributors(self):
        """按凭证号聚合，按 |difference| 降序。"""
        data = [
            {"voucher_no": "V001", "debit_total": 1000, "credit_total": 500},
            {"voucher_no": "V002", "debit_total": 200, "credit_total": 200},
            {"voucher_no": "V003", "debit_total": 800, "credit_total": 300},
        ]
        result = build_ledger_debit_credit_contributors(data)
        assert len(result) == 3
        # V001: diff=500, V003: diff=500, V002: diff=0
        assert result[0]["voucher_no"] in ("V001", "V003")
        assert result[2]["difference"] == 0
        # 必须有所有字段
        assert "voucher_no" in result[0]
        assert "debit_total" in result[0]
        assert "credit_total" in result[0]
        assert "difference" in result[0]

    def test_balance_vs_ledger_contributors(self):
        """按科目聚合，计算 expected_closing 和 difference。"""
        data = [
            {"account_code": "1001", "opening_balance": 100, "ledger_debit": 50, "ledger_credit": 30, "closing_balance": 130},
            {"account_code": "1002", "opening_balance": 200, "ledger_debit": 100, "ledger_credit": 100, "closing_balance": 200},
        ]
        result = build_balance_vs_ledger_contributors(data)
        assert len(result) == 2
        # 1001: expected=120, actual=130, diff=10
        acc_1001 = [r for r in result if r["account_code"] == "1001"][0]
        assert acc_1001["expected_closing"] == pytest.approx(120.0)
        assert acc_1001["difference"] == pytest.approx(10.0)

    def test_trial_balance_debit_credit_contributors(self):
        """按 standard_account_code 聚合。"""
        data = [
            {"standard_account_code": "1001", "direction": "debit", "amount": 100000, "direction_source": "explicit_direction", "difference_contribution": 5000},
            {"standard_account_code": "2001", "direction": "credit", "amount": 80000, "direction_source": "account_category_inferred", "difference_contribution": -3000},
        ]
        result = build_trial_balance_debit_credit_contributors(data)
        assert len(result) == 2
        # sorted by |difference_contribution| DESC
        assert abs(result[0]["difference_contribution"]) >= abs(result[1]["difference_contribution"])
        assert "direction_source" in result[0]

    def test_balance_sheet_equation_contributors(self):
        """报表行次。"""
        data = [
            {"report_line_code": "A01", "row_name": "资产合计", "amount": 5000000},
            {"report_line_code": "B01", "row_name": "负债合计", "amount": 4500000},
        ]
        result = build_balance_sheet_equation_contributors(data)
        assert len(result) == 2
        assert result[0]["report_line_code"] == "A01"

    def test_contributors_max_10(self):
        """贡献者最多返回 10 条。"""
        data = [{"voucher_no": f"V{i:03d}", "debit_total": i * 100, "credit_total": 0} for i in range(20)]
        result = build_ledger_debit_credit_contributors(data)
        assert len(result) == 10


# ---------------------------------------------------------------------------
# 3.7 排序：severity DESC, confidence DESC
# ---------------------------------------------------------------------------


class TestCauseSorting:
    """原因按 severity 和 confidence 排序。"""

    def test_sort_by_severity_desc_then_confidence_desc(self):
        """高 severity 排前，同 severity 按 confidence 降序。"""
        causes = [
            DiagnosticCause(cause_code="manual_review_required", severity=2, confidence=0.0, description="a"),
            DiagnosticCause(cause_code="source_data_unbalanced", severity=5, confidence=0.95, description="b"),
            DiagnosticCause(cause_code="sign_convention_anomaly", severity=4, confidence=0.8, description="c"),
            DiagnosticCause(cause_code="report_line_unmatched", severity=3, confidence=0.7, description="d"),
            DiagnosticCause(cause_code="pnl_not_closed_or_caliber_gap", severity=4, confidence=0.6, description="e"),
        ]
        sorted_causes = sort_causes(causes)

        # severity 5 first
        assert sorted_causes[0].cause_code == "source_data_unbalanced"
        assert sorted_causes[0].severity == 5

        # severity 4, confidence 0.8 before 0.6
        assert sorted_causes[1].severity == 4
        assert sorted_causes[1].confidence == 0.8
        assert sorted_causes[2].severity == 4
        assert sorted_causes[2].confidence == 0.6

        # severity 3
        assert sorted_causes[3].severity == 3

        # severity 2 last
        assert sorted_causes[4].cause_code == "manual_review_required"
        assert sorted_causes[4].severity == 2

    def test_sort_empty_list(self):
        """空列表排序不报错。"""
        assert sort_causes([]) == []

    def test_sort_single_item(self):
        """单项排序返回原样。"""
        cause = DiagnosticCause(cause_code="source_data_unbalanced", severity=5, confidence=0.9, description="x")
        assert sort_causes([cause]) == [cause]
