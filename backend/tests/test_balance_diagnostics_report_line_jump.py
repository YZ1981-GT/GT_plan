"""Tests for report_line_jump module.

Validates:
- 6.1 ReportLineMappingDialog 接收 account_code 定位参数
- 6.4 区分 seed_missing / unconfirmed / manual_error
- 6.5 跳转采用 dialog_prop transport 传参
- 6.6 诊断跳转后定位到指定科目（参数正确性）

Requirements: 6.1, 6.2, 6.4, 6.5
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.services.balance_diagnostics.report_line_jump import (
    MAPPING_STATUS_MANUAL_ERROR,
    MAPPING_STATUS_SEED_MISSING,
    MAPPING_STATUS_UNCONFIRMED,
    VALID_MAPPING_STATUSES,
    build_report_line_jump_params,
    build_report_line_jump_targets_batch,
)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestBuildReportLineJumpParams:
    """Test build_report_line_jump_params function."""

    def test_seed_missing_returns_dialog_prop_transport(self):
        """6.5: seed_missing 使用 dialog_prop transport。"""
        result = build_report_line_jump_params("2701", MAPPING_STATUS_SEED_MISSING)
        assert result.transport == "dialog_prop"
        assert result.target_type == "report_line_mapping"
        assert result.params["initialAccountCode"] == "2701"
        assert result.params["highlight"] == "true"
        assert result.params["mapping_status"] == "seed_missing"

    def test_unconfirmed_returns_correct_label(self):
        """6.4: unconfirmed 状态返回确认文案。"""
        result = build_report_line_jump_params("1122", MAPPING_STATUS_UNCONFIRMED)
        assert "确认" in result.label
        assert result.params["mapping_status"] == "unconfirmed"

    def test_manual_error_returns_correct_label(self):
        """6.4: manual_error 状态返回修正文案。"""
        result = build_report_line_jump_params("4001", MAPPING_STATUS_MANUAL_ERROR)
        assert "修正" in result.label
        assert result.params["mapping_status"] == "manual_error"

    def test_invalid_status_falls_back_to_seed_missing(self):
        """6.4: 无效状态回退到 seed_missing。"""
        result = build_report_line_jump_params("1001", "invalid_status")
        assert result.params["mapping_status"] == "seed_missing"

    def test_account_code_in_params(self):
        """6.1/6.6: account_code 作为 initialAccountCode 传入。"""
        result = build_report_line_jump_params("2701", MAPPING_STATUS_SEED_MISSING)
        assert result.params["initialAccountCode"] == "2701"


class TestBuildReportLineJumpTargetsBatch:
    """Test build_report_line_jump_targets_batch function."""

    def test_empty_accounts_returns_empty(self):
        """空列表返回空跳转列表。"""
        assert build_report_line_jump_targets_batch([]) == []

    def test_single_status_produces_one_target(self):
        """同 status 多科目只生成一个跳转。"""
        accounts = [
            {"account_code": "2701", "mapping_status": "seed_missing"},
            {"account_code": "2702", "mapping_status": "seed_missing"},
        ]
        targets = build_report_line_jump_targets_batch(accounts)
        assert len(targets) == 1
        assert targets[0].params["initialAccountCode"] == "2701"

    def test_multiple_statuses_produce_multiple_targets(self):
        """不同 status 分组生成多个跳转按钮。"""
        accounts = [
            {"account_code": "2701", "mapping_status": "seed_missing"},
            {"account_code": "1122", "mapping_status": "unconfirmed"},
            {"account_code": "4001", "mapping_status": "manual_error"},
        ]
        targets = build_report_line_jump_targets_batch(accounts)
        assert len(targets) == 3
        statuses = {t.params["mapping_status"] for t in targets}
        assert statuses == {"seed_missing", "unconfirmed", "manual_error"}

    def test_invalid_status_in_batch_normalized(self):
        """批量处理中无效 status 被标准化。"""
        accounts = [
            {"account_code": "1001", "mapping_status": "garbage"},
        ]
        targets = build_report_line_jump_targets_batch(accounts)
        assert len(targets) == 1
        assert targets[0].params["mapping_status"] == "seed_missing"


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


# Strategy for valid account codes (4-digit numeric strings)
account_code_st = st.from_regex(r"[1-9][0-9]{3}", fullmatch=True)
mapping_status_st = st.sampled_from(list(VALID_MAPPING_STATUSES))


class TestReportLineJumpProperties:
    """PBT: report_line_jump 不变量。"""

    @settings(max_examples=5)
    @given(code=account_code_st, status=mapping_status_st)
    def test_transport_always_dialog_prop(self, code: str, status: str):
        """**Validates: Requirements 6.5**

        Property: transport 始终为 dialog_prop（report_line_mapping 跳转闭环）。
        """
        result = build_report_line_jump_params(code, status)
        assert result.transport == "dialog_prop"

    @settings(max_examples=5)
    @given(code=account_code_st, status=mapping_status_st)
    def test_initial_account_code_always_present(self, code: str, status: str):
        """**Validates: Requirements 6.1**

        Property: 跳转参数始终包含 initialAccountCode = 传入的 account_code。
        """
        result = build_report_line_jump_params(code, status)
        assert result.params["initialAccountCode"] == code

    @settings(max_examples=5)
    @given(code=account_code_st, status=mapping_status_st)
    def test_target_type_always_report_line_mapping(self, code: str, status: str):
        """**Validates: Requirements 6.5**

        Property: target_type 固定为 report_line_mapping。
        """
        result = build_report_line_jump_params(code, status)
        assert result.target_type == "report_line_mapping"

    @settings(max_examples=5)
    @given(
        accounts=st.lists(
            st.fixed_dictionaries({
                "account_code": account_code_st,
                "mapping_status": mapping_status_st,
            }),
            min_size=0,
            max_size=10,
        )
    )
    def test_batch_target_count_le_status_count(self, accounts: list[dict]):
        """**Validates: Requirements 6.4**

        Property: 批量生成的跳转数 ≤ mapping_status 种类数。
        """
        targets = build_report_line_jump_targets_batch(accounts)
        unique_statuses = {a.get("mapping_status") for a in accounts}
        assert len(targets) <= len(unique_statuses)
