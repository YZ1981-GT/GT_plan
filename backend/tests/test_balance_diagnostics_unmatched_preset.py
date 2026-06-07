"""Tests for unmatched_preset module.

Validates:
- 8.1 一键预设流程返回 unmatched_accounts
- 8.2 有余额但 seed 查不到行次时不静默跳过
- 8.3 seed 升级刷新仅覆盖未确认 ai_suggested，保护 manual / reference_copied
- 8.4 长期负债、权益细分、损益类缺失时进入未匹配清单

Requirements: 5.4, 6.3
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.services.balance_diagnostics.unmatched_preset import (
    OVERWRITABLE_SOURCES,
    PROTECTED_SOURCES,
    get_unmatched_for_preset,
    refresh_seed_mappings,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_seed_data() -> list[dict]:
    """模拟 seed 数据（只覆盖部分科目）。"""
    return [
        {"standard_account_code": "1001", "report_line_code": "BS-002", "report_line_name": "货币资金"},
        {"standard_account_code": "1002", "report_line_code": "BS-002", "report_line_name": "货币资金"},
        {"standard_account_code": "1122", "report_line_code": "BS-008", "report_line_name": "应收账款"},
    ]


@pytest.fixture
def accounts_with_balance() -> list[dict]:
    """有余额的科目列表（含 seed 覆盖和不覆盖的）。"""
    return [
        {"account_code": "1001", "account_name": "库存现金", "amount": 50000.0},
        {"account_code": "1122", "account_name": "应收账款", "amount": 200000.0},
        {"account_code": "2701", "account_name": "长期应付款", "amount": 1000000.0},
        {"account_code": "4003", "account_name": "其他综合收益", "amount": 2373000.0},
        {"account_code": "6001", "account_name": "主营业务收入", "amount": 5000000.0},
    ]


# ---------------------------------------------------------------------------
# Unit tests: 8.1 / 8.2 get_unmatched_for_preset
# ---------------------------------------------------------------------------


class TestGetUnmatchedForPreset:
    """8.1/8.2: 获取未匹配科目清单。"""

    def test_returns_unmatched_accounts(self, accounts_with_balance, sample_seed_data):
        """8.1: 返回 seed 中查不到的科目。"""
        unmatched = get_unmatched_for_preset(accounts_with_balance, sample_seed_data)
        codes = [a.account_code for a in unmatched]
        # 2701, 4003, 6001 不在 seed 中
        assert "2701" in codes
        assert "4003" in codes
        assert "6001" in codes
        # 1001, 1122 在 seed 中
        assert "1001" not in codes
        assert "1122" not in codes

    def test_no_silent_skip(self, sample_seed_data):
        """8.2: 有余额但 seed 查不到时不静默跳过。"""
        accounts = [
            {"account_code": "2705", "account_name": "长期应付职工薪酬", "amount": 500000.0},
        ]
        unmatched = get_unmatched_for_preset(accounts, sample_seed_data)
        assert len(unmatched) == 1
        assert unmatched[0].account_code == "2705"
        assert unmatched[0].mapping_status == "seed_missing"

    def test_empty_accounts_returns_empty(self, sample_seed_data):
        unmatched = get_unmatched_for_preset([], sample_seed_data)
        assert unmatched == []

    def test_all_covered_returns_empty(self, sample_seed_data):
        accounts = [
            {"account_code": "1001", "account_name": "库存现金", "amount": 50000.0},
        ]
        unmatched = get_unmatched_for_preset(accounts, sample_seed_data)
        assert unmatched == []

    def test_mapping_status_is_seed_missing(self, sample_seed_data):
        """所有未匹配科目的 mapping_status 都是 seed_missing。"""
        accounts = [
            {"account_code": "9999", "account_name": "测试科目", "amount": 100.0},
        ]
        unmatched = get_unmatched_for_preset(accounts, sample_seed_data)
        for acc in unmatched:
            assert acc.mapping_status == "seed_missing"

    def test_long_term_liability_detected(self, sample_seed_data):
        """8.4: 长期负债缺失时进入未匹配清单。"""
        accounts = [
            {"account_code": "2701", "account_name": "长期应付款", "amount": 1000000.0},
        ]
        unmatched = get_unmatched_for_preset(accounts, sample_seed_data)
        assert len(unmatched) == 1
        assert unmatched[0].account_code == "2701"

    def test_equity_subdivision_detected(self, sample_seed_data):
        """8.4: 权益细分缺失时进入未匹配清单。"""
        accounts = [
            {"account_code": "4104", "account_name": "利润分配", "amount": 3000000.0},
        ]
        unmatched = get_unmatched_for_preset(accounts, sample_seed_data)
        assert len(unmatched) == 1
        assert unmatched[0].account_code == "4104"

    def test_pnl_missing_detected(self, sample_seed_data):
        """8.4: 损益类缺失时进入未匹配清单。"""
        accounts = [
            {"account_code": "6001", "account_name": "主营业务收入", "amount": 5000000.0},
            {"account_code": "6601", "account_name": "财务费用", "amount": 120000.0},
        ]
        unmatched = get_unmatched_for_preset(accounts, sample_seed_data)
        codes = [a.account_code for a in unmatched]
        assert "6001" in codes
        assert "6601" in codes


# ---------------------------------------------------------------------------
# Unit tests: 8.3 refresh_seed_mappings
# ---------------------------------------------------------------------------


class TestRefreshSeedMappings:
    """8.3: seed 升级刷新保护逻辑。"""

    def test_protected_manual_not_overwritten(self):
        """manual 映射不被覆盖。"""
        existing = [
            {"account_code": "1001", "report_line_code": "BS-002", "mapping_source": "manual"},
        ]
        new_seed = [
            {"standard_account_code": "1001", "report_line_code": "BS-099", "report_line_name": "新行次"},
        ]
        result = refresh_seed_mappings("proj-1", new_seed, existing)
        m1001 = next(m for m in result if m["account_code"] == "1001")
        # 保留原 manual 映射
        assert m1001["report_line_code"] == "BS-002"
        assert m1001["mapping_source"] == "manual"

    def test_protected_reference_copied_not_overwritten(self):
        """reference_copied 映射不被覆盖。"""
        existing = [
            {"account_code": "1002", "report_line_code": "BS-002", "mapping_source": "reference_copied"},
        ]
        new_seed = [
            {"standard_account_code": "1002", "report_line_code": "BS-099", "report_line_name": "新行次"},
        ]
        result = refresh_seed_mappings("proj-1", new_seed, existing)
        m1002 = next(m for m in result if m["account_code"] == "1002")
        assert m1002["report_line_code"] == "BS-002"
        assert m1002["mapping_source"] == "reference_copied"

    def test_ai_suggested_gets_overwritten(self):
        """ai_suggested 映射被新 seed 覆盖。"""
        existing = [
            {"account_code": "1122", "report_line_code": "BS-007", "mapping_source": "ai_suggested"},
        ]
        new_seed = [
            {"standard_account_code": "1122", "report_line_code": "BS-008", "report_line_name": "应收账款"},
        ]
        result = refresh_seed_mappings("proj-1", new_seed, existing)
        m1122 = next(m for m in result if m["account_code"] == "1122")
        assert m1122["report_line_code"] == "BS-008"
        assert m1122["mapping_source"] == "ai_suggested"

    def test_new_seed_entries_added(self):
        """新 seed 中有但现有映射中没有的科目 → 新增。"""
        existing = [
            {"account_code": "1001", "report_line_code": "BS-002", "mapping_source": "manual"},
        ]
        new_seed = [
            {"standard_account_code": "1001", "report_line_code": "BS-099"},
            {"standard_account_code": "2701", "report_line_code": "BS-050", "report_line_name": "长期应付款"},
        ]
        result = refresh_seed_mappings("proj-1", new_seed, existing)
        codes = [m["account_code"] for m in result]
        assert "2701" in codes
        m2701 = next(m for m in result if m["account_code"] == "2701")
        assert m2701["mapping_source"] == "ai_suggested"
        assert m2701["project_id"] == "proj-1"

    def test_empty_existing_all_from_seed(self):
        """无现有映射时全部从 seed 新增。"""
        new_seed = [
            {"standard_account_code": "1001", "report_line_code": "BS-002", "report_line_name": "货币资金"},
            {"standard_account_code": "1002", "report_line_code": "BS-002", "report_line_name": "货币资金"},
        ]
        result = refresh_seed_mappings("proj-1", new_seed, [])
        assert len(result) == 2
        for m in result:
            assert m["mapping_source"] == "ai_suggested"


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


account_code_st = st.from_regex(r"[1-9][0-9]{3}", fullmatch=True)


class TestUnmatchedPresetProperties:
    """PBT: unmatched_preset 不变量。"""

    @settings(max_examples=5)
    @given(
        account_codes=st.lists(account_code_st, min_size=1, max_size=8, unique=True),
        seed_codes=st.lists(account_code_st, min_size=0, max_size=5, unique=True),
    )
    def test_unmatched_is_complement_of_seed(
        self, account_codes: list[str], seed_codes: list[str]
    ):
        """**Validates: Requirements 5.4**

        Property: 未匹配科目 = 有余额科目 - seed 覆盖科目。
        """
        accounts = [{"account_code": c, "account_name": f"科目{c}", "amount": 100.0} for c in account_codes]
        seed = [{"standard_account_code": c} for c in seed_codes]
        unmatched = get_unmatched_for_preset(accounts, seed)
        unmatched_codes = {a.account_code for a in unmatched}
        expected = set(account_codes) - set(seed_codes)
        assert unmatched_codes == expected

    @settings(max_examples=5)
    @given(
        manual_codes=st.lists(account_code_st, min_size=1, max_size=3, unique=True),
        ai_codes=st.lists(account_code_st, min_size=1, max_size=3, unique=True),
    )
    def test_manual_never_overwritten(self, manual_codes: list[str], ai_codes: list[str]):
        """**Validates: Requirements 6.3**

        Property: manual 映射在 seed 刷新后保持不变。
        """
        existing = [
            {"account_code": c, "report_line_code": "BS-001", "mapping_source": "manual"}
            for c in manual_codes
        ]
        new_seed = [
            {"standard_account_code": c, "report_line_code": "BS-999", "report_line_name": "新"}
            for c in (manual_codes + ai_codes)
        ]
        result = refresh_seed_mappings("proj-test", new_seed, existing)
        for code in manual_codes:
            m = next((r for r in result if r["account_code"] == code), None)
            assert m is not None
            assert m["report_line_code"] == "BS-001"
            assert m["mapping_source"] == "manual"

    @settings(max_examples=5)
    @given(
        ai_codes=st.lists(account_code_st, min_size=1, max_size=5, unique=True),
    )
    def test_ai_suggested_always_overwritten_when_seed_has_entry(self, ai_codes: list[str]):
        """**Validates: Requirements 6.3**

        Property: ai_suggested 映射在新 seed 有对应条目时被覆盖。
        """
        existing = [
            {"account_code": c, "report_line_code": "BS-OLD", "mapping_source": "ai_suggested"}
            for c in ai_codes
        ]
        new_seed = [
            {"standard_account_code": c, "report_line_code": "BS-NEW", "report_line_name": "新行次"}
            for c in ai_codes
        ]
        result = refresh_seed_mappings("proj-test", new_seed, existing)
        for code in ai_codes:
            m = next((r for r in result if r["account_code"] == code), None)
            assert m is not None
            assert m["report_line_code"] == "BS-NEW"
