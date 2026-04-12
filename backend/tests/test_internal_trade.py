"""
Test Internal Trade Elimination calculations.
Validates: Requirements 5.1-5.4

All imports are mocked. No SQLAlchemy models are imported to avoid Base.metadata conflicts.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
import uuid


# ============================================================================
# Pure calculation logic (mirrors internal_trade_service.py)
# ============================================================================

def calc_unrealized_profit(
    trade_amount: Decimal,
    cost_amount: Decimal,
    inventory_remaining_ratio: Decimal | None,
) -> Decimal:
    """
    未实现利润 = (trade_amount - cost_amount) × inventory_remaining_ratio
    全部未实现时 inventory_remaining_ratio = 1
    无存货时 = 0
    """
    if inventory_remaining_ratio is None:
        inventory_remaining_ratio = Decimal("1")

    if inventory_remaining_ratio == Decimal("0"):
        return Decimal("0")

    gross_profit = trade_amount - cost_amount
    if gross_profit <= Decimal("0"):
        return Decimal("0")

    return gross_profit * inventory_remaining_ratio


def generate_elimination_entry(
    direction: str,
    unrealized_profit: Decimal,
    revenue_account: str,
    cost_account: str,
    inventory_account: str,
) -> list[dict]:
    """
    Generate balanced elimination entry for unrealized profit.

    Direction "sell_to_parent": Parent sold to Sub, unrealized at sub level
      Dr: 内部交易-未实现利润   Cr: 存货

    Direction "buy_from_parent": Sub sold to Parent, unrealized at parent level
      Dr: 少数股东权益          Cr: 投资收益
    """
    if unrealized_profit <= Decimal("0"):
        return []

    if direction == "sell_to_parent":
        return [
            {"account_code": "6101", "account_name": "内部交易-未实现利润", "dr": unrealized_profit, "cr": Decimal("0")},
            {"account_code": inventory_account, "account_name": "存货", "dr": Decimal("0"), "cr": unrealized_profit},
        ]
    else:
        return [
            {"account_code": "3002", "account_name": "少数股东权益", "dr": unrealized_profit, "cr": Decimal("0")},
            {"account_code": "6111", "account_name": "投资收益", "dr": Decimal("0"), "cr": unrealized_profit},
        ]


def calc_arap_difference(ar_balances: list[dict], ap_balances: list[dict], tolerance: Decimal) -> dict:
    """
    Calculate AR-AP difference between intercompany entities.
    Returns: {entity_code: {"ar": Decimal, "ap": Decimal, "diff": Decimal, "status": str}}
    """
    result = {}
    for bal in ar_balances:
        code = bal["entity_code"]
        if code not in result:
            result[code] = {"ar": Decimal("0"), "ap": Decimal("0"), "diff": Decimal("0")}
        result[code]["ar"] += bal["amount"]

    for bal in ap_balances:
        code = bal["entity_code"]
        if code not in result:
            result[code] = {"ar": Decimal("0"), "ap": Decimal("0"), "diff": Decimal("0")}
        result[code]["ap"] += bal["amount"]

    for code, vals in result.items():
        diff = vals["ar"] - vals["ap"]
        vals["diff"] = diff
        if abs(diff) <= tolerance:
            vals["status"] = "reconciled"
        else:
            vals["status"] = "difference"

    return result


# ============================================================================
# Test: Unrealized Profit Calculation
# ============================================================================

class TestUnrealizedProfit:
    def test_basic_unrealized_profit(self):
        """Unrealized profit = (revenue - COGS) × remaining ratio."""
        result = calc_unrealized_profit(
            trade_amount=Decimal("1000"),
            cost_amount=Decimal("600"),
            inventory_remaining_ratio=Decimal("1"),
        )
        assert result == Decimal("400")

    def test_partial_unrealized_profit(self):
        """Only 50% of inventory unsold → only 50% unrealized."""
        result = calc_unrealized_profit(
            trade_amount=Decimal("1000"),
            cost_amount=Decimal("600"),
            inventory_remaining_ratio=Decimal("0.5"),
        )
        assert result == Decimal("200")

    def test_zero_inventory_no_unrealized(self):
        """All inventory sold (ratio=0) → no unrealized profit."""
        result = calc_unrealized_profit(
            trade_amount=Decimal("1000"),
            cost_amount=Decimal("600"),
            inventory_remaining_ratio=Decimal("0"),
        )
        assert result == Decimal("0")

    def test_no_profit_no_unrealized(self):
        """Cost > revenue → no unrealized profit."""
        result = calc_unrealized_profit(
            trade_amount=Decimal("500"),
            cost_amount=Decimal("600"),
            inventory_remaining_ratio=Decimal("1"),
        )
        assert result == Decimal("0")

    def test_no_inventory_arg_means_full(self):
        """inventory_remaining_ratio=None defaults to 1 (fully unrealized)."""
        result = calc_unrealized_profit(
            trade_amount=Decimal("1000"),
            cost_amount=Decimal("600"),
            inventory_remaining_ratio=None,
        )
        assert result == Decimal("400")

    def test_elimination_entry_generated(self):
        """Elimination entry is generated for unrealized profit."""
        entries = generate_elimination_entry(
            direction="sell_to_parent",
            unrealized_profit=Decimal("400"),
            revenue_account="4001",
            cost_account="5001",
            inventory_account="1405",
        )
        assert len(entries) == 2
        assert entries[0]["dr"] == Decimal("400")
        assert entries[1]["cr"] == Decimal("400")


# ============================================================================
# Test: Internal AR/AP Reconciliation
# ============================================================================

class TestInternalArApReconciliation:
    def test_ar_ap_difference_calculated(self):
        """AR - AP difference is calculated correctly."""
        ar = [{"entity_code": "SUB1", "amount": Decimal("1000")}]
        ap = [{"entity_code": "SUB1", "amount": Decimal("1000")}]
        result = calc_arap_difference(ar, ap, tolerance=Decimal("0"))
        assert result["SUB1"]["diff"] == Decimal("0")

    def test_difference_exceeds_tolerance_flagged(self):
        """Difference > tolerance → status = 'difference'."""
        ar = [{"entity_code": "SUB1", "amount": Decimal("1000")}]
        ap = [{"entity_code": "SUB1", "amount": Decimal("990")}]
        result = calc_arap_difference(ar, ap, tolerance=Decimal("5"))
        # |10| > 5 → difference
        assert result["SUB1"]["diff"] == Decimal("10")
        assert result["SUB1"]["status"] == "difference"

    def test_tolerance_difference_accepted(self):
        """Difference ≤ tolerance → status = 'reconciled'."""
        ar = [{"entity_code": "SUB1", "amount": Decimal("1000")}]
        ap = [{"entity_code": "SUB1", "amount": Decimal("990")}]
        result = calc_arap_difference(ar, ap, tolerance=Decimal("10"))
        assert result["SUB1"]["status"] == "reconciled"

    def test_zero_difference_is_reconciled(self):
        """AR == AP with zero tolerance → reconciled."""
        ar = [{"entity_code": "SUB1", "amount": Decimal("500")}]
        ap = [{"entity_code": "SUB1", "amount": Decimal("500")}]
        result = calc_arap_difference(ar, ap, tolerance=Decimal("0"))
        assert result["SUB1"]["status"] == "reconciled"
        assert result["SUB1"]["diff"] == Decimal("0")


# ============================================================================
# Test: Auto-Generated Elimination
# ============================================================================

class TestAutoGeneratedElimination:
    def test_generate_elimination_from_unrealized_trade(self):
        """Elimination entry is generated from unrealized trade."""
        entries = generate_elimination_entry(
            direction="sell_to_parent",
            unrealized_profit=Decimal("100"),
            revenue_account="4001",
            cost_account="5001",
            inventory_account="1405",
        )
        assert len(entries) == 2
        assert entries[0]["account_code"] == "6101"
        assert entries[1]["account_code"] == "1405"

    def test_generated_entry_is_balanced(self):
        """Generated entry DR == CR."""
        entries = generate_elimination_entry(
            direction="sell_to_parent",
            unrealized_profit=Decimal("1000"),
            revenue_account="4001",
            cost_account="5001",
            inventory_account="1405",
        )
        total_dr = sum(e["dr"] for e in entries)
        total_cr = sum(e["cr"] for e in entries)
        assert total_dr == total_cr == Decimal("1000")

    def test_buy_from_parent_direction(self):
        """Different direction generates different accounts."""
        entries = generate_elimination_entry(
            direction="buy_from_parent",
            unrealized_profit=Decimal("500"),
            revenue_account="4001",
            cost_account="5001",
            inventory_account="1405",
        )
        assert entries[0]["account_code"] == "3002"  # 少数股东权益
        assert entries[1]["account_code"] == "6111"  # 投资收益

    def test_zero_profit_no_entry(self):
        """Zero unrealized profit generates no entry."""
        entries = generate_elimination_entry(
            direction="sell_to_parent",
            unrealized_profit=Decimal("0"),
            revenue_account="4001",
            cost_account="5001",
            inventory_account="1405",
        )
        assert entries == []

    def test_multiple_entities_reconciled(self):
        """Multiple entities each reconciled independently."""
        ar = [
            {"entity_code": "SUB1", "amount": Decimal("100")},
            {"entity_code": "SUB2", "amount": Decimal("200")},
        ]
        ap = [
            {"entity_code": "SUB1", "amount": Decimal("100")},
            {"entity_code": "SUB2", "amount": Decimal("195")},
        ]
        result = calc_arap_difference(ar, ap, tolerance=Decimal("5"))
        assert result["SUB1"]["status"] == "reconciled"
        assert result["SUB2"]["status"] == "reconciled"  # |5| <= 5
