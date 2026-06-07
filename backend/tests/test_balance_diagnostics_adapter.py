"""DataQualityService 口径统一适配器测试。

覆盖:
- 4.1 拆分 ledger_debit_credit_balance 与 trial_balance_debit_credit
- 4.2 report_balance 只表示 BS 勾稽
- 4.3 debit_credit_balance 兼容旧入口
- 4.4 返回 details 可转换为 BalanceDiagnosticsResult
- 4.5 损益未结转时不使用"资产=负债+权益"作为通用试算平衡
- 4.6 每个 caliber 的数据源和公式输出与设计一致
"""

import pytest

from backend.app.services.balance_diagnostics.data_quality_adapter import (
    CHECK_NAME_TO_CALIBER,
    adapt_all_results_to_diagnostics,
    adapt_check_result_to_diagnostics,
    adapt_legacy_check_name,
    get_caliber_for_check,
    is_report_balance_applicable,
)
from backend.app.services.balance_diagnostics.diagnostics_types import (
    CALIBER_DATA_SOURCES,
    CALIBER_LABELS,
    CALIBER_VALUES,
)


# ---------------------------------------------------------------------------
# 4.1 口径拆分
# ---------------------------------------------------------------------------


class TestCaliberMapping:
    """口径拆分与映射。"""

    def test_debit_credit_balance_maps_to_trial_balance(self):
        """旧 debit_credit_balance → trial_balance_debit_credit。"""
        assert get_caliber_for_check("debit_credit_balance") == "trial_balance_debit_credit"

    def test_ledger_debit_credit_balance_maps_correctly(self):
        """新 ledger_debit_credit_balance → ledger_debit_credit。"""
        assert get_caliber_for_check("ledger_debit_credit_balance") == "ledger_debit_credit"

    def test_balance_vs_ledger_unchanged(self):
        """balance_vs_ledger 保持不变。"""
        assert get_caliber_for_check("balance_vs_ledger") == "balance_vs_ledger"

    def test_report_balance_maps_to_equation(self):
        """report_balance → balance_sheet_equation。"""
        assert get_caliber_for_check("report_balance") == "balance_sheet_equation"

    def test_unknown_check_passes_through(self):
        """未知检查名称直接透传。"""
        assert get_caliber_for_check("some_new_check") == "some_new_check"


# ---------------------------------------------------------------------------
# 4.2 report_balance 只表示 BS 勾稽
# ---------------------------------------------------------------------------


class TestReportBalanceApplicability:
    """report_balance 仅报表生成后适用。"""

    def test_applicable_when_report_generated(self):
        assert is_report_balance_applicable(has_generated_report=True) is True

    def test_not_applicable_when_no_report(self):
        assert is_report_balance_applicable(has_generated_report=False) is False


# ---------------------------------------------------------------------------
# 4.3 兼容旧入口
# ---------------------------------------------------------------------------


class TestLegacyCompatibility:
    """debit_credit_balance 兼容旧入口。"""

    def test_legacy_check_returns_caliber_and_hint(self):
        """旧 debit_credit_balance 返回新 caliber + 口径提示。"""
        caliber, hint = adapt_legacy_check_name("debit_credit_balance")
        assert caliber == "trial_balance_debit_credit"
        assert hint is not None
        assert "trial_balance" in hint or "试算表" in hint

    def test_new_check_no_hint(self):
        """新口径无额外提示。"""
        caliber, hint = adapt_legacy_check_name("balance_vs_ledger")
        assert caliber == "balance_vs_ledger"
        assert hint is None


# ---------------------------------------------------------------------------
# 4.4 转换为 BalanceDiagnosticsResult
# ---------------------------------------------------------------------------


class TestAdaptToResult:
    """适配为 BalanceDiagnosticsResult。"""

    def test_debit_credit_balance_adapts(self):
        """debit_credit_balance 结果适配后 caliber 为 trial_balance_debit_credit。"""
        result = adapt_check_result_to_diagnostics(
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
        assert result.caliber == "trial_balance_debit_credit"
        assert result.caliber_label == CALIBER_LABELS["trial_balance_debit_credit"]
        assert result.difference == pytest.approx(50000.0)
        assert result.status == "blocking"
        # 数据源应包含 caliber_hint（因是旧入口）
        assert "caliber_hint" in result.data_sources

    def test_report_balance_adapts(self):
        """report_balance 适配后 caliber 为 balance_sheet_equation。"""
        result = adapt_check_result_to_diagnostics(
            "report_balance",
            {
                "status": "blocking",
                "message": "不平衡",
                "details": {
                    "asset_total": "5000000",
                    "liability_equity_total": "4900000",
                    "difference": "100000",
                },
            },
        )
        assert result.caliber == "balance_sheet_equation"
        assert result.asset_total == pytest.approx(5000000.0)
        assert result.liability_equity_total == pytest.approx(4900000.0)

    def test_balance_vs_ledger_adapts_with_top_contributors(self):
        """balance_vs_ledger 结果适配后包含 top_contributors。"""
        result = adapt_check_result_to_diagnostics(
            "balance_vs_ledger",
            {
                "status": "warning",
                "message": "2 科目不一致",
                "details": {
                    "checked": 100,
                    "passed": 98,
                    "differences": [
                        {
                            "account_code": "1001",
                            "account_name": "银行存款",
                            "opening_balance": "100",
                            "closing_balance": "130",
                            "debit_amount": "50",
                            "credit_amount": "30",
                            "expected_closing": "120",
                            "difference": "10",
                        },
                    ],
                },
            },
        )
        assert result.caliber == "balance_vs_ledger"
        assert len(result.top_contributors) == 1
        assert result.top_contributors[0]["account_code"] == "1001"

    def test_adapt_all_filters_non_balance(self):
        """adapt_all 只适配平衡类检查。"""
        results = {
            "debit_credit_balance": {"status": "passed", "details": {"debit_total": "100", "credit_total": "100", "difference": "0"}},
            "balance_vs_ledger": {"status": "passed", "details": {"checked": 10, "passed": 10, "differences": []}},
            "mapping_completeness": {"status": "warning", "details": {}},
            "report_balance": {"status": "passed", "details": {"asset_total": "100", "liability_equity_total": "100", "difference": "0"}},
            "profit_reconciliation": {"status": "passed", "details": {}},
        }
        diagnostics = adapt_all_results_to_diagnostics(results)
        assert len(diagnostics) == 3  # 只有 3 个平衡类
        calibers = [d.caliber for d in diagnostics]
        assert "trial_balance_debit_credit" in calibers
        assert "balance_vs_ledger" in calibers
        assert "balance_sheet_equation" in calibers


# ---------------------------------------------------------------------------
# 4.5 损益未结转时不使用"资产=负债+权益"作为通用试算平衡
# ---------------------------------------------------------------------------


class TestPnlNotClosedGuard:
    """损益未结转时口径限制。"""

    def test_report_balance_not_applicable_before_report(self):
        """报表未生成时 report_balance 不适用。"""
        assert is_report_balance_applicable(False) is False

    def test_balance_sheet_equation_data_source_mentions_report_only(self):
        """balance_sheet_equation 数据源描述明确仅报表生成后使用。"""
        ds = CALIBER_DATA_SOURCES["balance_sheet_equation"]
        assert "报表生成后" in ds["description"]
        assert ds["table_name"] == "financial_report"

    def test_trial_balance_is_independent_from_bs_equation(self):
        """trial_balance_debit_credit 独立于 balance_sheet_equation。"""
        trial_ds = CALIBER_DATA_SOURCES["trial_balance_debit_credit"]
        bs_ds = CALIBER_DATA_SOURCES["balance_sheet_equation"]
        assert trial_ds["table_name"] != bs_ds["table_name"]
        assert trial_ds["formula"] != bs_ds["formula"]


# ---------------------------------------------------------------------------
# 4.6 每个 caliber 的数据源和公式输出与设计一致
# ---------------------------------------------------------------------------


class TestCaliberDataSourcesConsistency:
    """验证数据源和公式与设计文档一致。"""

    def test_all_calibers_have_data_sources(self):
        """每个 caliber 都有数据源定义。"""
        for cal in CALIBER_VALUES:
            assert cal in CALIBER_DATA_SOURCES

    def test_ledger_debit_credit_source(self):
        """ledger_debit_credit: tb_ledger, SUM debit == SUM credit。"""
        ds = CALIBER_DATA_SOURCES["ledger_debit_credit"]
        assert ds["table_name"] == "tb_ledger"
        assert "SUM" in ds["formula"]
        assert "debit_amount" in ds["formula"]
        assert "credit_amount" in ds["formula"]
        assert ds["top_contributors_source"] == "voucher_no"

    def test_trial_balance_debit_credit_source(self):
        """trial_balance_debit_credit: trial_balance, 按方向汇总。"""
        ds = CALIBER_DATA_SOURCES["trial_balance_debit_credit"]
        assert ds["table_name"] == "trial_balance"
        assert "方向" in ds["formula"]
        assert ds["top_contributors_source"] == "standard_account_code"

    def test_balance_vs_ledger_source(self):
        """balance_vs_ledger: tb_balance + tb_ledger, closing = opening + debit - credit。"""
        ds = CALIBER_DATA_SOURCES["balance_vs_ledger"]
        assert "tb_balance" in ds["table_name"]
        assert "tb_ledger" in ds["table_name"]
        assert "closing_balance" in ds["formula"]
        assert "opening_balance" in ds["formula"]
        assert ds["top_contributors_source"] == "account_code"

    def test_balance_sheet_equation_source(self):
        """balance_sheet_equation: financial_report, 资产合计 = 负债所有者权益合计。"""
        ds = CALIBER_DATA_SOURCES["balance_sheet_equation"]
        assert ds["table_name"] == "financial_report"
        assert "资产" in ds["formula"]
        assert "负债" in ds["formula"] or "权益" in ds["formula"]
        assert ds["top_contributors_source"] == "report_line_code"

    def test_all_data_sources_have_required_keys(self):
        """每个数据源包含 table_name / formula / description / top_contributors_source。"""
        required_keys = {"table_name", "formula", "description", "top_contributors_source"}
        for cal in CALIBER_VALUES:
            ds = CALIBER_DATA_SOURCES[cal]
            missing = required_keys - set(ds.keys())
            assert not missing, f"caliber {cal} 缺少 keys: {missing}"

    def test_all_calibers_have_labels(self):
        """每个 caliber 有中文标签。"""
        for cal in CALIBER_VALUES:
            assert cal in CALIBER_LABELS
            assert len(CALIBER_LABELS[cal]) > 0
