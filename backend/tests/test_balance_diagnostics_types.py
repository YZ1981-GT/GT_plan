"""DTO fixture 测试：确保前后端字段一致。

验证 BalanceDiagnosticsResult、DiagnosticCause、DiagnosticJumpTarget 的字段和枚举
与前端 TypeScript 定义保持一致。

Requirements: 1.1, 1.3, 1.4, 1.5
"""

import json
from pathlib import Path

import pytest

from backend.app.services.balance_diagnostics.diagnostics_types import (
    CALIBER_DATA_SOURCES,
    CALIBER_LABELS,
    CALIBER_VALUES,
    CAUSE_CODE_VALUES,
    JUMP_TARGET_TYPE_VALUES,
    TRANSPORT_VALUES,
    BalanceDiagnosticsResult,
    DiagnosticCause,
    DiagnosticJumpTarget,
    UnmatchedAccount,
)


# ---------------------------------------------------------------------------
# Fixture：标准诊断结果样例
# ---------------------------------------------------------------------------

FIXTURE_DIAGNOSTIC_RESULT = {
    "caliber": "ledger_debit_credit",
    "caliber_label": "序时账凭证借贷合计",
    "status": "blocking",
    "difference": 44030236.47,
    "debit_total": 2546171215.70,
    "credit_total": 2502140979.23,
    "asset_total": None,
    "liability_equity_total": None,
    "likely_causes": [
        {
            "cause_code": "source_data_unbalanced",
            "severity": 5,
            "confidence": 0.9,
            "description": "序时账凭证借贷发生额不平，差异 44,030,236.47 元",
            "evidence": {"top_vouchers": ["V001", "V002"]},
        }
    ],
    "unmatched_accounts": [
        {
            "account_code": "2701",
            "account_name": "长期应付款",
            "amount": 1000.00,
            "mapping_status": "seed_missing",
        }
    ],
    "sign_anomalies": [],
    "sign_anomalies_unavailable": False,
    "top_contributors": [
        {"voucher_no": "V001", "debit_total": 100000, "credit_total": 50000, "difference": 50000}
    ],
    "jump_targets": [
        {
            "target_type": "report_line_mapping",
            "label": "查看报表行次映射",
            "transport": "dialog_prop",
            "params": {"account_code": "2701", "highlight": "true"},
        }
    ],
    "data_sources": {
        "table_name": "tb_ledger",
        "formula": "SUM(debit_amount) == SUM(credit_amount)",
        "description": "序时账全部凭证借方发生额合计应等于贷方发生额合计",
    },
}


class TestDiagnosticsTypesFixture:
    """验证 DTO 可正确构造和序列化。"""

    def test_balance_diagnostics_result_from_fixture(self):
        """fixture 数据能成功构造 BalanceDiagnosticsResult。"""
        result = BalanceDiagnosticsResult(**FIXTURE_DIAGNOSTIC_RESULT)
        assert result.caliber == "ledger_debit_credit"
        assert result.caliber_label == "序时账凭证借贷合计"
        assert result.status == "blocking"
        assert result.difference == pytest.approx(44030236.47)
        assert len(result.likely_causes) == 1
        assert len(result.unmatched_accounts) == 1
        assert len(result.jump_targets) == 1

    def test_diagnostic_cause_validation(self):
        """DiagnosticCause severity 和 confidence 边界。"""
        cause = DiagnosticCause(
            cause_code="report_line_unmatched",
            severity=3,
            confidence=0.75,
            description="存在未匹配报表行次的科目",
            evidence={"count": 5},
        )
        assert cause.severity == 3
        assert cause.confidence == 0.75

    def test_diagnostic_cause_severity_bounds(self):
        """severity 超出范围应报错。"""
        with pytest.raises(Exception):
            DiagnosticCause(
                cause_code="report_line_unmatched",
                severity=6,  # invalid
                confidence=0.5,
                description="test",
            )

    def test_diagnostic_jump_target_with_transport(self):
        """DiagnosticJumpTarget 包含 transport 字段。"""
        target = DiagnosticJumpTarget(
            target_type="report_line_mapping",
            label="查看报表行次映射",
            transport="dialog_prop",
            params={"account_code": "2701", "highlight": "true"},
        )
        assert target.transport == "dialog_prop"
        assert target.params["account_code"] == "2701"

    def test_unmatched_account(self):
        """UnmatchedAccount 基本构造。"""
        acc = UnmatchedAccount(
            account_code="4003",
            account_name="其他综合收益",
            amount=2373000.0,
            mapping_status="seed_missing",
        )
        assert acc.mapping_status == "seed_missing"


class TestCaliberEnumConsistency:
    """确保枚举值和标签一致。"""

    def test_all_calibers_have_labels(self):
        """每个 caliber 都有中文标签。"""
        for cal in CALIBER_VALUES:
            assert cal in CALIBER_LABELS, f"caliber {cal} 缺少中文标签"
            assert len(CALIBER_LABELS[cal]) > 0

    def test_all_calibers_have_data_sources(self):
        """每个 caliber 都有数据源定义。"""
        for cal in CALIBER_VALUES:
            assert cal in CALIBER_DATA_SOURCES, f"caliber {cal} 缺少数据源定义"
            ds = CALIBER_DATA_SOURCES[cal]
            assert "table_name" in ds
            assert "formula" in ds
            assert "description" in ds
            assert "top_contributors_source" in ds

    def test_cause_code_values_complete(self):
        """原因代码枚举完整。"""
        assert len(CAUSE_CODE_VALUES) == 5
        assert "report_line_unmatched" in CAUSE_CODE_VALUES
        assert "manual_review_required" in CAUSE_CODE_VALUES

    def test_jump_target_values_complete(self):
        """跳转目标类型枚举完整。"""
        assert len(JUMP_TARGET_TYPE_VALUES) == 4
        assert "report_line_mapping" in JUMP_TARGET_TYPE_VALUES

    def test_transport_values_complete(self):
        """传参方式枚举完整。"""
        assert len(TRANSPORT_VALUES) == 3
        assert "dialog_prop" in TRANSPORT_VALUES
        assert "route_query" in TRANSPORT_VALUES
        assert "event_payload" in TRANSPORT_VALUES


class TestFrontendBackendFieldConsistency:
    """验证前后端字段名称和枚举一致性（通过解析 TS 文件）。"""

    @pytest.fixture
    def ts_file_content(self) -> str:
        # 从 backend/tests/ 向上两级到仓库根
        ts_path = Path(__file__).resolve().parents[2] / "audit-platform" / "frontend" / "src" / "types" / "balance-diagnostics.ts"
        if not ts_path.exists():
            pytest.skip("前端 TS 文件不存在")
        return ts_path.read_text(encoding="utf-8")

    def test_caliber_values_in_ts(self, ts_file_content: str):
        """前端 TS 包含所有 caliber 值。"""
        for cal in CALIBER_VALUES:
            assert cal in ts_file_content, f"前端缺少 caliber: {cal}"

    def test_cause_code_values_in_ts(self, ts_file_content: str):
        """前端 TS 包含所有 cause_code 值。"""
        for code in CAUSE_CODE_VALUES:
            assert code in ts_file_content, f"前端缺少 cause_code: {code}"

    def test_jump_target_values_in_ts(self, ts_file_content: str):
        """前端 TS 包含所有跳转目标类型。"""
        for jt in JUMP_TARGET_TYPE_VALUES:
            assert jt in ts_file_content, f"前端缺少 jump_target: {jt}"

    def test_transport_values_in_ts(self, ts_file_content: str):
        """前端 TS 包含所有 transport 值。"""
        for t in TRANSPORT_VALUES:
            assert t in ts_file_content, f"前端缺少 transport: {t}"

    def test_key_fields_in_ts(self, ts_file_content: str):
        """前端 TS 包含 BalanceDiagnosticsResult 关键字段名。"""
        key_fields = [
            "caliber",
            "caliber_label",
            "status",
            "difference",
            "debit_total",
            "credit_total",
            "likely_causes",
            "unmatched_accounts",
            "sign_anomalies",
            "sign_anomalies_unavailable",
            "top_contributors",
            "jump_targets",
            "data_sources",
        ]
        for field in key_fields:
            assert field in ts_file_content, f"前端缺少字段: {field}"
