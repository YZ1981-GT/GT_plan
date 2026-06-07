"""BalanceDiagnosticsService 测试。

覆盖:
- 2.1 validator findings 转换
- 2.2 DataQualityService 结果转换
- 2.3 未匹配科目检测
- 2.4 符号异常构建
- 2.5 跳转目标生成
- 2.6 graceful degrade
- 2.7 符号异常不可用时仍能输出未匹配科目和源数据不平原因
"""

import pytest

from backend.app.services.balance_diagnostics.diagnostics_service import (
    build_full_diagnostics,
    build_jump_targets,
    build_sign_anomalies,
    build_sign_anomaly_unavailable_cause,
    build_unmatched_accounts,
    convert_data_quality_result_to_diagnostics,
    convert_validator_finding_to_diagnostics,
)
from backend.app.services.balance_diagnostics.diagnostics_types import (
    DiagnosticCause,
    UnmatchedAccount,
)


# ---------------------------------------------------------------------------
# 2.1 validator findings 转换
# ---------------------------------------------------------------------------


class TestConvertValidatorFinding:
    """validator findings → 诊断 DTO。"""

    def test_balance_unbalanced_converts(self):
        """BALANCE_UNBALANCED → ledger_debit_credit caliber。"""
        finding = {
            "code": "BALANCE_UNBALANCED",
            "message": "序时账借贷不平衡",
            "explanation": {
                "inputs": {"sum_debit": 1000000, "sum_credit": 950000},
                "computed": {},
                "sample_voucher_ids": ["V001", "V002", "V003"],
            },
        }
        result = convert_validator_finding_to_diagnostics(finding)
        assert result is not None
        assert result.caliber == "ledger_debit_credit"
        assert result.caliber_label == "序时账凭证借贷合计"
        assert result.status == "blocking"
        assert result.difference == pytest.approx(50000.0)
        assert result.debit_total == pytest.approx(1000000.0)
        assert result.credit_total == pytest.approx(950000.0)
        assert len(result.likely_causes) == 1
        assert result.likely_causes[0].cause_code == "source_data_unbalanced"
        assert len(result.top_contributors) == 3

    def test_balance_ledger_mismatch_converts(self):
        """BALANCE_LEDGER_MISMATCH → balance_vs_ledger caliber。"""
        finding = {
            "code": "BALANCE_LEDGER_MISMATCH",
            "message": "余额表与序时账不一致",
            "explanation": {
                "diff_breakdown": {
                    "opening": 100,
                    "sum_debit": 50,
                    "sum_credit": 30,
                    "actual_closing": 130,
                },
                "account_code": "1001",
            },
        }
        result = convert_validator_finding_to_diagnostics(finding)
        assert result is not None
        assert result.caliber == "balance_vs_ledger"
        assert result.status == "blocking"
        # expected_closing = 100 + 50 - 30 = 120, actual = 130, diff = 10
        assert result.difference == pytest.approx(10.0)
        assert len(result.top_contributors) == 1
        assert result.top_contributors[0]["account_code"] == "1001"

    def test_non_balance_finding_returns_none(self):
        """非平衡类 finding 返回 None。"""
        finding = {"code": "ACCOUNT_NOT_IN_CHART", "message": "test"}
        assert convert_validator_finding_to_diagnostics(finding) is None


# ---------------------------------------------------------------------------
# 2.2 DataQualityService 结果转换
# ---------------------------------------------------------------------------


class TestConvertDataQualityResult:
    """DataQualityService 结果 → 诊断 DTO。"""

    def test_debit_credit_balance_converts(self):
        """debit_credit_balance → trial_balance_debit_credit。"""
        result = convert_data_quality_result_to_diagnostics(
            "debit_credit_balance",
            {
                "status": "blocking",
                "message": "借贷不平衡",
                "details": {
                    "debit_total": "2000000",
                    "credit_total": "1950000",
                    "difference": "50000",
                },
            },
        )
        assert result is not None
        assert result.caliber == "trial_balance_debit_credit"
        assert result.difference == pytest.approx(50000.0)
        assert result.debit_total == pytest.approx(2000000.0)

    def test_report_balance_converts(self):
        """report_balance → balance_sheet_equation。"""
        result = convert_data_quality_result_to_diagnostics(
            "report_balance",
            {
                "status": "blocking",
                "message": "资产负债表不平衡",
                "details": {
                    "asset_total": "5000000",
                    "liability_equity_total": "4900000",
                    "difference": "100000",
                },
            },
        )
        assert result is not None
        assert result.caliber == "balance_sheet_equation"
        assert result.asset_total == pytest.approx(5000000.0)
        assert result.liability_equity_total == pytest.approx(4900000.0)

    def test_mapping_completeness_returns_none(self):
        """mapping_completeness 非平衡类，返回 None。"""
        result = convert_data_quality_result_to_diagnostics(
            "mapping_completeness",
            {"status": "warning", "details": {}},
        )
        assert result is None

    def test_passed_status_no_jump_targets(self):
        """passed 状态不生成跳转目标。"""
        result = convert_data_quality_result_to_diagnostics(
            "debit_credit_balance",
            {
                "status": "passed",
                "message": "借贷平衡",
                "details": {"debit_total": "100", "credit_total": "100", "difference": "0"},
            },
        )
        assert result is not None
        assert result.jump_targets == []


# ---------------------------------------------------------------------------
# 2.3 未匹配科目检测
# ---------------------------------------------------------------------------


class TestBuildUnmatchedAccounts:
    """未匹配报表行次科目检测。"""

    def test_identifies_unmapped_accounts(self):
        """有余额但无映射的科目进入清单。"""
        accounts = [
            {"account_code": "1001", "account_name": "银行存款", "amount": 100000},
            {"account_code": "2701", "account_name": "长期应付款", "amount": 50000},
            {"account_code": "4003", "account_name": "其他综合收益", "amount": 2373000},
        ]
        mapped = {"1001"}  # 只有 1001 已映射
        result = build_unmatched_accounts(accounts, mapped)
        assert len(result) == 2
        codes = [a.account_code for a in result]
        assert "2701" in codes
        assert "4003" in codes

    def test_empty_accounts_returns_empty(self):
        """无科目时返回空列表。"""
        assert build_unmatched_accounts([], set()) == []


# ---------------------------------------------------------------------------
# 2.4 符号异常构建
# ---------------------------------------------------------------------------


class TestBuildSignAnomalies:
    """符号异常构建。"""

    def test_none_flags_returns_unavailable(self):
        """sign_anomaly_flags 为 None 时标记不可用。"""
        anomalies, unavailable = build_sign_anomalies(None)
        assert anomalies == []
        assert unavailable is True

    def test_with_dict_flags(self):
        """dict 列表正常返回。"""
        flags = [
            {"account_code": "2221", "expected_direction": "credit", "actual_direction": "debit"}
        ]
        anomalies, unavailable = build_sign_anomalies(flags)
        assert len(anomalies) == 1
        assert unavailable is False

    def test_empty_list_returns_available(self):
        """空列表表示已检查但无异常。"""
        anomalies, unavailable = build_sign_anomalies([])
        assert anomalies == []
        assert unavailable is False


# ---------------------------------------------------------------------------
# 2.5 跳转目标生成
# ---------------------------------------------------------------------------


class TestBuildJumpTargets:
    """跳转目标生成。"""

    def test_with_unmatched_accounts(self):
        """有未匹配科目时生成 report_line_mapping 跳转。"""
        targets = build_jump_targets(
            caliber="trial_balance_debit_credit",
            has_unmatched_accounts=True,
            unmatched_account_codes=["2701", "4003"],
        )
        target_types = [t.target_type for t in targets]
        assert "report_line_mapping" in target_types
        mapping_target = [t for t in targets if t.target_type == "report_line_mapping"][0]
        assert mapping_target.transport == "dialog_prop"
        assert mapping_target.params["account_code"] == "2701"

    def test_with_sign_anomalies(self):
        """有符号异常时生成 sign_anomaly_review 跳转。"""
        targets = build_jump_targets(
            caliber="ledger_debit_credit",
            has_sign_anomalies=True,
        )
        target_types = [t.target_type for t in targets]
        assert "sign_anomaly_review" in target_types

    def test_always_has_ledger_penetration(self):
        """始终包含 ledger_penetration 跳转。"""
        targets = build_jump_targets(caliber="ledger_debit_credit")
        target_types = [t.target_type for t in targets]
        assert "ledger_penetration" in target_types


# ---------------------------------------------------------------------------
# 2.6 + 2.7 graceful degrade
# ---------------------------------------------------------------------------


class TestGracefulDegrade:
    """符号异常不可用时的 graceful degrade。"""

    def test_sign_anomaly_unavailable_cause(self):
        """生成不阻断的提示性原因。"""
        cause = build_sign_anomaly_unavailable_cause()
        assert cause.cause_code == "manual_review_required"
        assert cause.severity == 1
        assert cause.confidence == 0.0

    def test_full_diagnostics_with_unavailable_sign_anomalies(self):
        """2.7: 符号异常不可用时仍能输出未匹配科目和源数据不平原因。"""
        unmatched = [
            UnmatchedAccount(account_code="2701", account_name="长期应付款", amount=50000),
        ]
        causes = [
            DiagnosticCause(
                cause_code="source_data_unbalanced",
                severity=5,
                confidence=0.9,
                description="序时账借贷不平",
                evidence={},
            ),
            DiagnosticCause(
                cause_code="report_line_unmatched",
                severity=3,
                confidence=0.7,
                description="存在未匹配科目",
                evidence={"count": 1},
            ),
        ]

        result = build_full_diagnostics(
            caliber="ledger_debit_credit",
            status="blocking",
            difference=50000.0,
            debit_total=1000000.0,
            credit_total=950000.0,
            likely_causes=causes,
            unmatched_accounts=unmatched,
            sign_anomaly_flags=None,  # 不可用
        )

        # 核心断言：不阻断其他诊断
        assert result.sign_anomalies_unavailable is True
        assert result.sign_anomalies == []

        # 未匹配科目仍然输出
        assert len(result.unmatched_accounts) == 1
        assert result.unmatched_accounts[0].account_code == "2701"

        # 源数据不平原因仍然输出
        cause_codes = [c.cause_code for c in result.likely_causes]
        assert "source_data_unbalanced" in cause_codes
        assert "report_line_unmatched" in cause_codes

        # graceful degrade 加入了一条 manual_review_required 提示
        assert "manual_review_required" in cause_codes

        # 跳转目标包含 report_line_mapping（因有未匹配科目）
        target_types = [t.target_type for t in result.jump_targets]
        assert "report_line_mapping" in target_types
        assert "ledger_penetration" in target_types
