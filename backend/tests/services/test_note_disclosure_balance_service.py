"""附注披露平衡规则校验服务测试

测试 NoteDisclosureBalanceService 的规则解析、计算和质量清单生成。

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_disclosure_balance_service import (
    BalanceRule,
    NoteDisclosureBalanceService,
)
from app.services.note_quality_checklist_service import QualityChecklistItem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> NoteDisclosureBalanceService:
    return NoteDisclosureBalanceService()


def _make_rule(
    rule_id: str = "test_rule",
    section_id: str = "accounts_receivable",
    left: str = "sum(note.accounts_receivable.aging_analysis.*.closing_balance)",
    right: str = "report.BS.accounts_receivable.closing_balance",
    tolerance: str = "0.01",
    severity: str = "blocking",
    description: str = "测试规则",
) -> BalanceRule:
    return BalanceRule({
        "rule_id": rule_id,
        "section_id": section_id,
        "left": left,
        "right": right,
        "tolerance": tolerance,
        "severity": severity,
        "description": description,
    })


# ---------------------------------------------------------------------------
# Unit Tests: 应收账款
# ---------------------------------------------------------------------------


class TestAccountsReceivableTieout:
    """应收账款平衡规则测试"""

    def test_balanced_no_items(self, service: NoteDisclosureBalanceService):
        """附注合计等于报表数，无差异"""
        rule = _make_rule()
        note_data = {
            "accounts_receivable": {
                "aging_analysis": [
                    {"closing_balance": "100.00"},
                    {"closing_balance": "200.00"},
                    {"closing_balance": "300.00"},
                ]
            }
        }
        report_data = {
            "BS": {
                "accounts_receivable": {"closing_balance": "600.00"}
            }
        }
        items = service.check_balance_rules([rule], note_data, report_data)
        assert items == []

    def test_difference_creates_tieout_item(self, service: NoteDisclosureBalanceService):
        """附注合计与报表数不一致，生成 tieout 条目"""
        rule = _make_rule()
        note_data = {
            "accounts_receivable": {
                "aging_analysis": [
                    {"closing_balance": "100.00"},
                    {"closing_balance": "200.00"},
                ]
            }
        }
        report_data = {
            "BS": {
                "accounts_receivable": {"closing_balance": "500.00"}
            }
        }
        items = service.check_balance_rules([rule], note_data, report_data)
        assert len(items) == 1
        item = items[0]
        assert item.level == "blocking"
        assert item.category == "tieout"
        assert item.section_id == "accounts_receivable"
        assert item.evidence is not None
        assert item.evidence["diff"] == "200.00"

    def test_within_tolerance_no_items(self, service: NoteDisclosureBalanceService):
        """差异在容差内，无 tieout 条目"""
        rule = _make_rule(tolerance="1.00")
        note_data = {
            "accounts_receivable": {
                "aging_analysis": [
                    {"closing_balance": "599.50"},
                ]
            }
        }
        report_data = {
            "BS": {
                "accounts_receivable": {"closing_balance": "600.00"}
            }
        }
        items = service.check_balance_rules([rule], note_data, report_data)
        assert items == []


# ---------------------------------------------------------------------------
# Unit Tests: 固定资产
# ---------------------------------------------------------------------------


class TestFixedAssetsTieout:
    """固定资产平衡规则测试"""

    def test_fa_balanced(self, service: NoteDisclosureBalanceService):
        rule = _make_rule(
            rule_id="fa_closing",
            section_id="fixed_assets",
            left="sum(note.fixed_assets.category_analysis.*.closing_net_value)",
            right="report.BS.fixed_assets.closing_balance",
            description="固定资产期末余额核对",
        )
        note_data = {
            "fixed_assets": {
                "category_analysis": [
                    {"closing_net_value": "1000000.00"},
                    {"closing_net_value": "500000.00"},
                ]
            }
        }
        report_data = {
            "BS": {
                "fixed_assets": {"closing_balance": "1500000.00"}
            }
        }
        items = service.check_balance_rules([rule], note_data, report_data)
        assert items == []

    def test_fa_difference(self, service: NoteDisclosureBalanceService):
        rule = _make_rule(
            rule_id="fa_closing",
            section_id="fixed_assets",
            left="sum(note.fixed_assets.category_analysis.*.closing_net_value)",
            right="report.BS.fixed_assets.closing_balance",
            description="固定资产期末余额核对",
        )
        note_data = {
            "fixed_assets": {
                "category_analysis": [
                    {"closing_net_value": "1000000.00"},
                ]
            }
        }
        report_data = {
            "BS": {
                "fixed_assets": {"closing_balance": "1500000.00"}
            }
        }
        items = service.check_balance_rules([rule], note_data, report_data)
        assert len(items) == 1
        assert items[0].section_id == "fixed_assets"
        assert items[0].category == "tieout"


# ---------------------------------------------------------------------------
# Unit Tests: 关联方余额
# ---------------------------------------------------------------------------


class TestRelatedPartyBalanceTieout:
    """关联方余额平衡规则测试"""

    def test_rp_balanced(self, service: NoteDisclosureBalanceService):
        rule = _make_rule(
            rule_id="rp_receivable",
            section_id="related_party",
            left="sum(note.related_party.balances.*.closing_balance)",
            right="report.BS.other_receivables_related.closing_balance",
            severity="warning",
            description="关联方应收余额核对",
        )
        note_data = {
            "related_party": {
                "balances": [
                    {"closing_balance": "50000.00"},
                    {"closing_balance": "30000.00"},
                ]
            }
        }
        report_data = {
            "BS": {
                "other_receivables_related": {"closing_balance": "80000.00"}
            }
        }
        items = service.check_balance_rules([rule], note_data, report_data)
        assert items == []

    def test_rp_difference_is_warning(self, service: NoteDisclosureBalanceService):
        rule = _make_rule(
            rule_id="rp_receivable",
            section_id="related_party",
            left="sum(note.related_party.balances.*.closing_balance)",
            right="report.BS.other_receivables_related.closing_balance",
            severity="warning",
            description="关联方应收余额核对",
        )
        note_data = {
            "related_party": {
                "balances": [
                    {"closing_balance": "50000.00"},
                ]
            }
        }
        report_data = {
            "BS": {
                "other_receivables_related": {"closing_balance": "80000.00"}
            }
        }
        items = service.check_balance_rules([rule], note_data, report_data)
        assert len(items) == 1
        assert items[0].level == "warning"
        assert items[0].category == "tieout"


# ---------------------------------------------------------------------------
# Unit Tests: 数据缺失场景
# ---------------------------------------------------------------------------


class TestMissingData:
    """数据缺失测试"""

    def test_note_data_missing_section(self, service: NoteDisclosureBalanceService):
        rule = _make_rule()
        note_data = {}  # 无 accounts_receivable
        report_data = {
            "BS": {"accounts_receivable": {"closing_balance": "600.00"}}
        }
        items = service.check_balance_rules([rule], note_data, report_data)
        assert len(items) == 1
        assert items[0].category == "completeness"
        assert "附注" in items[0].message

    def test_report_data_missing_item(self, service: NoteDisclosureBalanceService):
        rule = _make_rule()
        note_data = {
            "accounts_receivable": {
                "aging_analysis": [{"closing_balance": "100.00"}]
            }
        }
        report_data = {"BS": {}}  # 无 accounts_receivable
        items = service.check_balance_rules([rule], note_data, report_data)
        assert len(items) == 1
        assert items[0].category == "completeness"
        assert "报表" in items[0].message

    def test_empty_rules_returns_empty(self, service: NoteDisclosureBalanceService):
        items = service.check_balance_rules([], {}, {})
        assert items == []


# ---------------------------------------------------------------------------
# Unit Tests: load_rules
# ---------------------------------------------------------------------------


class TestLoadRules:
    """规则加载测试"""

    def test_load_default_rules(self, service: NoteDisclosureBalanceService):
        rules = service.load_rules()
        assert len(rules) >= 4
        rule_ids = {r.rule_id for r in rules}
        assert "ar_closing_balance_tieout" in rule_ids
        assert "fa_closing_balance_tieout" in rule_ids
        assert "rp_receivable_balance_tieout" in rule_ids

    def test_rules_have_valid_severity(self, service: NoteDisclosureBalanceService):
        rules = service.load_rules()
        for rule in rules:
            assert rule.severity in ("blocking", "warning", "info")

    def test_rules_have_valid_tolerance(self, service: NoteDisclosureBalanceService):
        rules = service.load_rules()
        for rule in rules:
            assert rule.tolerance >= Decimal("0")


# ---------------------------------------------------------------------------
# Unit Tests: manual override 尊重
# ---------------------------------------------------------------------------


class TestManualOverrideRespect:
    """Validates: Requirement 6.5 - 校验尊重 manual override"""

    def test_manual_override_still_checked(self, service: NoteDisclosureBalanceService):
        """即使有 manual override，差异仍会被报出（但提示复核人关注）"""
        rule = _make_rule()
        note_data = {
            "accounts_receivable": {
                "aging_analysis": [
                    {"closing_balance": "999.00"},  # manual override 值
                ]
            }
        }
        report_data = {
            "BS": {
                "accounts_receivable": {"closing_balance": "600.00"}
            }
        }
        items = service.check_balance_rules([rule], note_data, report_data)
        assert len(items) == 1
        assert items[0].category == "tieout"


# ---------------------------------------------------------------------------
# Property-Based Test
# ---------------------------------------------------------------------------

st_amount = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("99999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@settings(max_examples=5)
@given(
    amounts=st.lists(st_amount, min_size=1, max_size=5),
    tolerance=st.decimals(
        min_value=Decimal("0.01"),
        max_value=Decimal("100"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_balanced_data_never_produces_tieout(
    amounts: list[Decimal],
    tolerance: Decimal,
):
    """**Validates: Requirements 6.2**

    Property: When left sum equals right value, no tieout item is generated.
    """
    total = sum(amounts)
    rule = _make_rule(tolerance=str(tolerance))
    note_data = {
        "accounts_receivable": {
            "aging_analysis": [
                {"closing_balance": str(a)} for a in amounts
            ]
        }
    }
    report_data = {
        "BS": {
            "accounts_receivable": {"closing_balance": str(total)}
        }
    }
    service = NoteDisclosureBalanceService()
    items = service.check_balance_rules([rule], note_data, report_data)
    tieout_items = [i for i in items if i.category == "tieout"]
    assert tieout_items == []
