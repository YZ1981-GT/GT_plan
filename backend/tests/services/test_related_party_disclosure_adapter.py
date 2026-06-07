"""关联方披露专项适配器测试

测试 RelatedPartyDisclosureAdapter 的数据适配、tie-out 和质量清单生成。

Validates: Requirements 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.related_party_disclosure_adapter import (
    RelatedPartyDisclosureAdapter,
    RelatedPartyDisclosureResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter() -> RelatedPartyDisclosureAdapter:
    return RelatedPartyDisclosureAdapter()


# ---------------------------------------------------------------------------
# 测试数据
# ---------------------------------------------------------------------------

SAMPLE_PARTIES = [
    {
        "party_id": "rp_001",
        "party_name": "A 公司",
        "relationship_type": "母公司",
        "relationship_description": "控股母公司",
    },
    {
        "party_id": "rp_002",
        "party_name": "B 公司",
        "relationship_type": "子公司",
        "relationship_description": "全资子公司",
    },
]

SAMPLE_TRANSACTIONS = [
    {
        "party_id": "rp_001",
        "transaction_type": "采购",
        "current_amount": "500000.00",
        "prior_amount": "400000.00",
    },
    {
        "party_id": "rp_002",
        "transaction_type": "销售",
        "current_amount": "300000.00",
        "prior_amount": "250000.00",
    },
]

SAMPLE_BALANCES = [
    {
        "party_id": "rp_001",
        "balance_type": "receivable",
        "closing_balance": "100000.00",
        "opening_balance": "80000.00",
    },
    {
        "party_id": "rp_002",
        "balance_type": "payable",
        "closing_balance": "50000.00",
        "opening_balance": "40000.00",
    },
]

SAMPLE_EVIDENCES = [
    {
        "party_id": "rp_001",
        "has_confirmation": True,
        "has_attachment": True,
        "confirmation_status": "confirmed",
    },
    {
        "party_id": "rp_002",
        "has_confirmation": False,
        "has_attachment": True,
        "confirmation_status": "not_sent",
    },
]


# ---------------------------------------------------------------------------
# Unit Tests: 主体适配
# ---------------------------------------------------------------------------


class TestPartiesAdapt:
    """关联方主体适配测试"""

    def test_adapts_parties(self, adapter: RelatedPartyDisclosureAdapter):
        result = adapter.adapt(SAMPLE_PARTIES, [], [], [])
        assert len(result.parties) == 2
        assert result.parties[0].party_id == "rp_001"
        assert result.parties[0].party_name == "A 公司"
        assert result.parties[0].relationship_type == "母公司"

    def test_empty_parties(self, adapter: RelatedPartyDisclosureAdapter):
        result = adapter.adapt([], [], [], [])
        assert result.parties == []

    def test_missing_relationship_generates_warning(self, adapter: RelatedPartyDisclosureAdapter):
        """Requirement 9.4: 缺少关系类型"""
        parties = [{"party_id": "rp_x", "party_name": "X 公司"}]
        result = adapter.adapt(parties, [], [], [])
        quality_items = [i for i in result.quality_items if i.category == "completeness"]
        assert any("缺少关系类型" in item.message for item in quality_items)


# ---------------------------------------------------------------------------
# Unit Tests: 交易适配
# ---------------------------------------------------------------------------


class TestTransactionsAdapt:
    """关联方交易适配测试"""

    def test_adapts_transactions(self, adapter: RelatedPartyDisclosureAdapter):
        result = adapter.adapt([], SAMPLE_TRANSACTIONS, [], [])
        assert len(result.transactions) == 2
        assert result.transactions[0].party_id == "rp_001"
        assert result.transactions[0].transaction_type == "采购"
        assert result.transactions[0].current_amount == Decimal("500000.00")


# ---------------------------------------------------------------------------
# Unit Tests: 余额适配
# ---------------------------------------------------------------------------


class TestBalancesAdapt:
    """关联方余额适配测试"""

    def test_adapts_balances(self, adapter: RelatedPartyDisclosureAdapter):
        result = adapter.adapt([], [], SAMPLE_BALANCES, [])
        assert len(result.balances) == 2
        assert result.balances[0].balance_type == "receivable"
        assert result.balances[0].closing_balance == Decimal("100000.00")

    def test_balance_without_transaction_generates_warning(self, adapter: RelatedPartyDisclosureAdapter):
        """Requirement 9.4: 有余额无交易"""
        balances = [{"party_id": "rp_x", "balance_type": "receivable", "closing_balance": "1000.00"}]
        result = adapter.adapt([], [], balances, [])
        completeness_items = [i for i in result.quality_items if "无交易记录" in i.message]
        assert len(completeness_items) == 1


# ---------------------------------------------------------------------------
# Unit Tests: 证据适配
# ---------------------------------------------------------------------------


class TestEvidencesAdapt:
    """证据标识适配测试"""

    def test_adapts_evidences(self, adapter: RelatedPartyDisclosureAdapter):
        result = adapter.adapt([], [], [], SAMPLE_EVIDENCES)
        assert len(result.evidences) == 2
        assert result.evidences[0].has_confirmation is True
        assert result.evidences[1].has_confirmation is False

    def test_balance_without_evidence_generates_info(self, adapter: RelatedPartyDisclosureAdapter):
        """有余额但无函证或附件"""
        balances = [{"party_id": "rp_x", "balance_type": "receivable", "closing_balance": "5000.00"}]
        result = adapter.adapt([], [], balances, [])
        info_items = [i for i in result.quality_items if "缺少函证或附件" in i.message]
        assert len(info_items) == 1


# ---------------------------------------------------------------------------
# Unit Tests: Tie-out
# ---------------------------------------------------------------------------


class TestTieout:
    """关联方余额与报表项目 tie-out 测试"""

    def test_balanced_receivable(self, adapter: RelatedPartyDisclosureAdapter):
        """Requirement 9.3: 余额一致"""
        balances = [
            {"party_id": "rp_001", "balance_type": "receivable", "closing_balance": "100000.00"},
            {"party_id": "rp_002", "balance_type": "receivable", "closing_balance": "50000.00"},
        ]
        report_data = {
            "other_receivables_related": {"closing_balance": "150000.00"}
        }
        result = adapter.adapt([], [], balances, [], report_data=report_data)
        receivable_tieout = [t for t in result.tieout_results if "应收" in t.rule_description]
        assert len(receivable_tieout) == 1
        assert receivable_tieout[0].is_balanced is True

    def test_unbalanced_receivable_creates_quality_item(self, adapter: RelatedPartyDisclosureAdapter):
        """Requirement 9.3: 余额不一致进入质量清单"""
        balances = [
            {"party_id": "rp_001", "balance_type": "receivable", "closing_balance": "100000.00"},
        ]
        report_data = {
            "other_receivables_related": {"closing_balance": "200000.00"}
        }
        result = adapter.adapt([], [], balances, [], report_data=report_data)
        tieout_items = [i for i in result.quality_items if i.category == "tieout"]
        assert len(tieout_items) == 1
        assert "差异" in tieout_items[0].message

    def test_balanced_payable(self, adapter: RelatedPartyDisclosureAdapter):
        balances = [
            {"party_id": "rp_001", "balance_type": "payable", "closing_balance": "80000.00"},
        ]
        report_data = {
            "other_payables_related": {"closing_balance": "80000.00"}
        }
        result = adapter.adapt([], [], balances, [], report_data=report_data)
        payable_tieout = [t for t in result.tieout_results if "应付" in t.rule_description]
        assert len(payable_tieout) == 1
        assert payable_tieout[0].is_balanced is True

    def test_no_report_data_no_tieout(self, adapter: RelatedPartyDisclosureAdapter):
        """无报表数据时不做 tieout"""
        balances = [
            {"party_id": "rp_001", "balance_type": "receivable", "closing_balance": "100000.00"},
        ]
        result = adapter.adapt([], [], balances, [])
        assert result.tieout_results == []


# ---------------------------------------------------------------------------
# Unit Tests: 全链路
# ---------------------------------------------------------------------------


class TestFullAdapt:
    """全链路适配测试"""

    def test_full_adapt_returns_all_fields(self, adapter: RelatedPartyDisclosureAdapter):
        report_data = {
            "other_receivables_related": {"closing_balance": "100000.00"},
            "other_payables_related": {"closing_balance": "50000.00"},
        }
        result = adapter.adapt(
            SAMPLE_PARTIES,
            SAMPLE_TRANSACTIONS,
            SAMPLE_BALANCES,
            SAMPLE_EVIDENCES,
            report_data=report_data,
        )
        assert isinstance(result, RelatedPartyDisclosureResult)
        assert len(result.parties) == 2
        assert len(result.transactions) == 2
        assert len(result.balances) == 2
        assert len(result.evidences) == 2
        assert len(result.tieout_results) >= 1


# ---------------------------------------------------------------------------
# Property-Based Test
# ---------------------------------------------------------------------------

st_decimal_amount = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("9999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@settings(max_examples=5)
@given(
    receivable_amounts=st.lists(st_decimal_amount, min_size=1, max_size=4),
)
def test_tieout_balanced_when_report_equals_sum(
    receivable_amounts: list[Decimal],
):
    """**Validates: Requirements 9.3**

    Property: When report amount equals sum of balances, tieout is balanced.
    """
    total = sum(receivable_amounts)
    balances = [
        {"party_id": f"rp_{i}", "balance_type": "receivable", "closing_balance": str(a)}
        for i, a in enumerate(receivable_amounts)
    ]
    report_data = {
        "other_receivables_related": {"closing_balance": str(total)}
    }
    adapter = RelatedPartyDisclosureAdapter()
    result = adapter.adapt([], [], balances, [], report_data=report_data)
    receivable_tieouts = [t for t in result.tieout_results if "应收" in t.rule_description]
    assert len(receivable_tieouts) == 1
    assert receivable_tieouts[0].is_balanced is True
    tieout_quality = [i for i in result.quality_items if i.category == "tieout"]
    assert tieout_quality == []
