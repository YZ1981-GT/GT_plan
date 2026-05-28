"""Sprint B.0.9 — consol_elimination_rules 单元测试.

覆盖：
- get_elimination_rules 注册表
- get_rule 单规则获取
- apply_elimination 抵销应用
- calculate_elimination_amount 金额计算
- validate_wp_code_exists CI-17 校验
- validate_all_rules_wp_codes 全量校验

Validates: Requirements D12, CI-17
"""

from __future__ import annotations

import pytest
from decimal import Decimal

from app.services.consol_elimination_rules import (
    ELIMINATION_RULES,
    VALID_WP_CODES,
    get_elimination_rules,
    get_rule,
    apply_elimination,
    calculate_elimination_amount,
    validate_wp_code_exists,
    validate_all_rules_wp_codes,
)


# ---------------------------------------------------------------------------
# 注册表测试
# ---------------------------------------------------------------------------


class TestEliminationRulesRegistry:
    """抵销规则注册表测试."""

    def test_four_preset_rules(self):
        rules = get_elimination_rules()
        assert len(rules) == 4
        assert "internal_ar" in rules
        assert "internal_revenue" in rules
        assert "internal_inventory_unrealized" in rules
        assert "internal_dividend" in rules

    def test_rule_structure(self):
        rule = get_rule("internal_ar")
        assert rule is not None
        assert rule["name"] == "内部应收账款抵销"
        assert rule["wp_code"] == "consol_internal_ar"
        assert rule["match_logic"] == "by_company_pair"
        assert "affects_columns" in rule
        assert "category" in rule

    def test_get_rule_unknown(self):
        assert get_rule("nonexistent") is None

    def test_valid_wp_codes_set(self):
        assert len(VALID_WP_CODES) == 4
        assert "consol_internal_ar" in VALID_WP_CODES
        assert "consol_internal_revenue" in VALID_WP_CODES
        assert "consol_internal_inventory" in VALID_WP_CODES
        assert "consol_internal_dividend" in VALID_WP_CODES


# ---------------------------------------------------------------------------
# apply_elimination 测试
# ---------------------------------------------------------------------------


class TestApplyElimination:
    """apply_elimination 抵销应用测试."""

    def test_basic_elimination(self):
        result = apply_elimination(
            aggregated_value=Decimal("1000"),
            rule_type="internal_ar",
            wp_data={"elimination_amount": 200},
        )
        assert result == Decimal("800.00")

    def test_elimination_no_wp_data(self):
        result = apply_elimination(
            aggregated_value=Decimal("1000"),
            rule_type="internal_ar",
            wp_data=None,
        )
        assert result == Decimal("1000.00")

    def test_elimination_unknown_rule(self):
        result = apply_elimination(
            aggregated_value=Decimal("500"),
            rule_type="unknown_rule",
            wp_data={"elimination_amount": 100},
        )
        assert result == Decimal("500")

    def test_elimination_with_float(self):
        result = apply_elimination(
            aggregated_value=1000.50,
            rule_type="internal_revenue",
            wp_data={"amount": 300.25},
        )
        assert result == Decimal("700.25")

    def test_elimination_zero_amount(self):
        result = apply_elimination(
            aggregated_value=Decimal("500"),
            rule_type="internal_ar",
            wp_data={"elimination_amount": 0},
        )
        assert result == Decimal("500.00")


# ---------------------------------------------------------------------------
# calculate_elimination_amount 测试
# ---------------------------------------------------------------------------


class TestCalculateEliminationAmount:
    """calculate_elimination_amount 金额计算测试."""

    def test_from_wp_cache(self):
        ctx = {
            "_wp_cache": {
                "consol_internal_ar": {"elimination_amount": 500},
            }
        }
        result = calculate_elimination_amount(
            rule_type="internal_ar",
            child_projects=[],
            ctx=ctx,
        )
        assert result == Decimal("500")

    def test_by_company_pair(self):
        children = [
            {"internal_balance": 100},
            {"internal_balance": 100},
        ]
        result = calculate_elimination_amount(
            rule_type="internal_ar",
            child_projects=children,
            ctx={},
        )
        # 双向 / 2 = 100
        assert result == Decimal("100.00")

    def test_by_inventory_margin(self):
        children = [
            {"unrealized_profit": 50},
            {"unrealized_profit": 30},
        ]
        result = calculate_elimination_amount(
            rule_type="internal_inventory_unrealized",
            child_projects=children,
            ctx={},
        )
        assert result == Decimal("80")

    def test_by_dividend(self):
        children = [
            {"internal_dividend": 200},
        ]
        result = calculate_elimination_amount(
            rule_type="internal_dividend",
            child_projects=children,
            ctx={},
        )
        assert result == Decimal("200")

    def test_unknown_rule(self):
        result = calculate_elimination_amount(
            rule_type="nonexistent",
            child_projects=[],
            ctx={},
        )
        assert result == Decimal("0")


# ---------------------------------------------------------------------------
# CI-17 校验测试
# ---------------------------------------------------------------------------


class TestValidateWpCode:
    """CI-17 wp_code 校验测试."""

    def test_valid_rule(self):
        assert validate_wp_code_exists("internal_ar") is True
        assert validate_wp_code_exists("internal_revenue") is True
        assert validate_wp_code_exists("internal_inventory_unrealized") is True
        assert validate_wp_code_exists("internal_dividend") is True

    def test_invalid_rule(self):
        assert validate_wp_code_exists("nonexistent") is False

    def test_all_rules_valid(self):
        invalid = validate_all_rules_wp_codes()
        assert invalid == []
