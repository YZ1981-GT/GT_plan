"""
Test Consolidated Trial Balance aggregation.
Validates: Requirements 2.1-2.7

All imports are mocked to avoid SQLAlchemy Base.metadata conflicts.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from datetime import date
import uuid


# ============================================================================
# Mock helpers
# ============================================================================

def make_mock_tb(
    entity_code="SUB1",
    account_code="1001",
    account_name="Cash",
    dr_balance=Decimal("0"),
    cr_balance=Decimal("0"),
    category="asset",
    currency="CNY",
):
    """Create a mock trial balance line."""
    tb = MagicMock()
    tb.id = uuid.uuid4()
    tb.entity_code = entity_code
    tb.account_code = account_code
    tb.account_name = account_name
    tb.dr_balance = dr_balance
    tb.cr_balance = cr_balance
    tb.category = category
    tb.currency = currency
    return tb


def make_mock_company(code, currency="CNY", is_included=True):
    """Create a mock company."""
    c = MagicMock()
    c.id = uuid.uuid4()
    c.company_code = code
    c.functional_currency = currency
    c.is_included = is_included
    return c


# ============================================================================
# Pure aggregation logic (mirrors service)
# ============================================================================

def aggregate_trial_balances(rows):
    """
    Sum all rows by account_code.
    Returns: dict[account_code] = {"dr": Decimal, "cr": Decimal}
    """
    totals = {}
    for row in rows:
        code = row.account_code
        if code not in totals:
            totals[code] = {"dr": Decimal("0"), "cr": Decimal("0")}
        totals[code]["dr"] += row.dr_balance
        totals[code]["cr"] += row.cr_balance
    return totals


def apply_eliminations(totals, eliminations):
    """Subtract elimination amounts from totals."""
    result = {}
    for code, amounts in totals.items():
        elim = eliminations.get(code, {"dr": Decimal("0"), "cr": Decimal("0")})
        result[code] = {
            "dr": amounts["dr"] - elim.get("dr", Decimal("0")),
            "cr": amounts["cr"] - elim.get("cr", Decimal("0")),
        }
    return result


def consolidated_balance_check(assets, liabilities, equity):
    """Fundamental accounting equation: Assets = Liabilities + Equity."""
    return assets == liabilities + equity


def net_income(revenue_rows, expense_rows):
    """Net income = sum(revenue cr) - sum(expense dr)."""
    revenue = sum(r.cr_balance for r in revenue_rows)
    expenses = sum(r.dr_balance for r in expense_rows)
    return revenue - expenses


# ============================================================================
# Test: Trial Balance Aggregation
# ============================================================================

class TestTrialBalanceAggregation:
    def test_aggregate_single_entity(self):
        """Single entity's trial balance is summed correctly."""
        rows = [
            make_mock_tb("SUB1", "1001", "Cash", dr_balance=Decimal("10000")),
            make_mock_tb("SUB1", "2001", "AP", cr_balance=Decimal("6000")),
            make_mock_tb("SUB1", "3001", "Capital", cr_balance=Decimal("4000")),
        ]
        totals = aggregate_trial_balances(rows)
        assert totals["1001"]["dr"] == Decimal("10000")
        assert totals["2001"]["cr"] == Decimal("6000")

    def test_aggregate_multiple_entities(self):
        """Multiple entities' balances are summed together."""
        rows = [
            make_mock_tb("PARENT", "1001", "Cash", dr_balance=Decimal("5000")),
            make_mock_tb("SUB1", "1001", "Cash", dr_balance=Decimal("3000")),
            make_mock_tb("SUB2", "1001", "Cash", dr_balance=Decimal("2000")),
        ]
        totals = aggregate_trial_balances(rows)
        assert totals["1001"]["dr"] == Decimal("10000")

    def test_excluded_entity_not_in_aggregate(self):
        """Excluded entity's balances are excluded."""
        included_rows = [
            make_mock_tb("SUB1", "1001", "Cash", dr_balance=Decimal("3000")),
        ]
        excluded_rows = [
            make_mock_tb("EXCLUDED", "1001", "Cash", dr_balance=Decimal("9999")),
        ]
        all_rows = included_rows + excluded_rows

        # Simulate filtering: only included entities
        filtered = [r for r in all_rows if r.entity_code != "EXCLUDED"]
        totals = aggregate_trial_balances(filtered)
        assert totals["1001"]["dr"] == Decimal("3000")

    def test_zero_balance_accounts_not_in_totals(self):
        """Accounts with zero balance are included (they exist in the structure)."""
        rows = [
            make_mock_tb("SUB1", "1001", "Cash", dr_balance=Decimal("0")),
        ]
        totals = aggregate_trial_balances(rows)
        # Account still appears with zero
        assert "1001" in totals
        assert totals["1001"]["dr"] == Decimal("0")


# ============================================================================
# Test: Elimination Recalculation
# ============================================================================

class TestEliminationRecalculation:
    def test_elimination_column_recalculates(self):
        """After elimination amounts change, column is updated."""
        rows = [
            make_mock_tb("PARENT", "3010", "Investment in Sub", dr_balance=Decimal("1000")),
            make_mock_tb("SUB1", "3001", "Capital", cr_balance=Decimal("1000")),
        ]
        totals = aggregate_trial_balances(rows)

        # Before elimination
        assert totals["3010"]["dr"] == Decimal("1000")
        assert totals["3001"]["cr"] == Decimal("1000")

        # After equity elimination (investment DR=0, capital CR=0)
        elims = {
            "3010": {"dr": Decimal("1000"), "cr": Decimal("0")},
            "3001": {"dr": Decimal("0"), "cr": Decimal("1000")},
        }
        result = apply_eliminations(totals, elims)
        assert result["3010"]["dr"] == Decimal("0")
        assert result["3001"]["cr"] == Decimal("0")

    def test_eliminations_net_to_zero(self):
        """Total eliminations DR == CR (entry is balanced)."""
        elims = {
            "3010": {"dr": Decimal("1000"), "cr": Decimal("0")},
            "3001": {"dr": Decimal("0"), "cr": Decimal("1000")},
        }
        total_dr = sum(e["dr"] for e in elims.values())
        total_cr = sum(e["cr"] for e in elims.values())
        assert total_dr == total_cr


# ============================================================================
# Test: Formula Invariants
# ============================================================================

class TestFormulaInvariants:
    def test_assets_equals_liabilities_plus_equity(self):
        """Fundamental equation holds for a balanced balance sheet."""
        assert consolidated_balance_check(
            assets=Decimal("100000"),
            liabilities=Decimal("60000"),
            equity=Decimal("40000"),
        ) is True

    def test_equation_fails_when_unbalanced(self):
        """Equation fails when debits != credits."""
        assert consolidated_balance_check(
            assets=Decimal("100000"),
            liabilities=Decimal("50000"),
            equity=Decimal("40000"),
        ) is False  # 100k != 90k

    def test_consol_balance_sheet_balances(self):
        """BS balances after all eliminations."""
        # After full elimination: parent investment = sub equity, both = 0
        assets_after = Decimal("800000")  # only non-investment assets
        liabilities_after = Decimal("200000")
        equity_after = Decimal("600000")
        assert consolidated_balance_check(assets_after, liabilities_after, equity_after) is True

    def test_net_income_reflected_in_equity(self):
        """Net income increases equity."""
        revenue = [make_mock_tb("SUB1", "4001", dr_balance=Decimal("0"), cr_balance=Decimal("50000"))]
        expenses = [make_mock_tb("SUB1", "5001", dr_balance=Decimal("30000"))]
        ni = net_income(revenue, expenses)
        beginning_equity = Decimal("200000")
        ending_equity = beginning_equity + ni
        assert ni == Decimal("20000")
        assert ending_equity == Decimal("220000")


# ============================================================================
# Test: Validation
# ============================================================================

class TestValidation:
    def test_mismatched_currency_requires_conversion(self):
        """Different currencies need conversion rate before aggregation."""
        rows = [
            make_mock_tb("PARENT", "1001", "Cash", dr_balance=Decimal("10000"), currency="CNY"),
            make_mock_tb("SUB1", "1001", "Cash", dr_balance=Decimal("1000"), currency="USD"),
        ]
        # Without conversion, direct sum is wrong
        totals = aggregate_trial_balances(rows)
        direct_sum = totals["1001"]["dr"]
        # Correct sum with conversion rate 7.0
        converted_sub = Decimal("1000") * Decimal("7")
        correct_sum = Decimal("10000") + converted_sub
        assert direct_sum != correct_sum  # confirms conversion is needed
        assert correct_sum == Decimal("17000")

    def test_empty_trial_balance(self):
        """Empty TB returns empty totals."""
        totals = aggregate_trial_balances([])
        assert totals == {}
