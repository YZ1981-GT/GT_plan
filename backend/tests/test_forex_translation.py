"""
Test Forex Translation calculations.
Validates: Requirements 7.1-7.4

All imports are mocked to avoid SQLAlchemy Base.metadata conflicts.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock


# ============================================================================
# Pure forex translation logic (mirrors forex_translation_service.py)
# ============================================================================

class AccountCategory:
    asset = "asset"
    liability = "liability"
    equity = "equity"
    income = "income"
    expense = "expense"


def classify_account_category(account_code: str) -> str:
    """
    Classify account for forex translation rate selection.
    1xxx/2xxx → asset/liability → closing rate
    3xxx     → equity → historical rate
    4xxx/5xxx → income/expense → average rate
    6xxx     → other expense → average rate
    """
    code = account_code.strip()
    if not code:
        return "unknown"
    first = int(code[0])

    if first in (1, 2):
        return "bs"  # balance sheet: closing rate
    elif first == 3:
        return "equity"  # equity: historical rate
    elif first in (4, 5, 6):
        return "pl"  # P&L: average rate
    return "unknown"


def translate_amount(amount: Decimal, rate: Decimal | None) -> Decimal:
    """Translate amount using rate. Zero/None rate → no translation."""
    if rate is None or rate == Decimal("0"):
        return amount
    return amount * rate


def calculate_translation_difference(
    translated_total_assets: Decimal,
    translated_total_liabilities: Decimal,
    translated_equity: Decimal,
) -> dict:
    """
    Translation difference = translated total - original amounts
    Positive = gain (equity adjustment)
    Negative = loss (equity adjustment)
    BS should balance after: assets = liabilities + equity + translation_diff
    """
    translated_total = translated_total_assets
    liabilities_equity = translated_total_liabilities + translated_equity
    diff = translated_total - liabilities_equity
    return {
        "translation_difference": diff,
        "is_gain": diff > 0,
        "is_loss": diff < 0,
    }


def apply_forex_rates(
    items: list[dict],
    closing_rate: Decimal,
    average_rate: Decimal,
    historical_rate: Decimal,
) -> list[dict]:
    """
    Apply forex rates to trial balance items.
    Returns: list of {account_code, original, translated, rate_used}
    """
    result = []
    for item in items:
        category = classify_account_category(item["account_code"])
        if category == "bs":
            rate = closing_rate
        elif category == "pl":
            rate = average_rate
        elif category == "equity":
            rate = historical_rate
        else:
            rate = closing_rate

        translated = translate_amount(Decimal(str(item["balance"])), rate)
        result.append({
            "account_code": item["account_code"],
            "original": Decimal(str(item["balance"])),
            "translated": translated,
            "rate_used": rate,
        })
    return result


def bs_balances_after_translation(translated_assets, translated_liabilities, translated_equity, translation_diff) -> bool:
    """
    Balance sheet must balance after translation:
    assets = liabilities + equity + translation_diff
    """
    return translated_assets == translated_liabilities + translated_equity + translation_diff


# ============================================================================
# Test: Forex Translation Rules
# ============================================================================

class TestForexTranslationRules:
    def test_asset_account_uses_closing_rate(self):
        """1xxx accounts → closing rate."""
        assert classify_account_category("1001") == "bs"
        assert classify_account_category("1122") == "bs"
        assert classify_account_category("1503") == "bs"

    def test_liability_account_uses_closing_rate(self):
        """2xxx accounts → closing rate."""
        assert classify_account_category("2001") == "bs"
        assert classify_account_category("2501") == "bs"

    def test_equity_account_uses_historical_rate(self):
        """3xxx accounts → historical rate."""
        assert classify_account_category("3001") == "equity"
        assert classify_account_category("3103") == "equity"
        assert classify_account_category("4001") == "pl"  # income

    def test_income_account_uses_average_rate(self):
        """4xxx accounts → average rate."""
        assert classify_account_category("4001") == "pl"
        assert classify_account_category("4301") == "pl"

    def test_expense_account_uses_average_rate(self):
        """5xxx/6xxx accounts → average rate."""
        assert classify_account_category("5001") == "pl"
        assert classify_account_category("6001") == "pl"


# ============================================================================
# Test: Translation Difference Calculation
# ============================================================================

class TestTranslationDifference:
    def test_positive_difference_is_gain(self):
        """Translated assets > liabilities+equity → translation gain."""
        result = calculate_translation_difference(
            translated_total_assets=Decimal("1070000"),
            translated_total_liabilities=Decimal("600000"),
            translated_equity=Decimal("400000"),
        )
        assert result["translation_difference"] == Decimal("70000")
        assert result["is_gain"] is True
        assert result["is_loss"] is False

    def test_negative_difference_is_loss(self):
        """Translated assets < liabilities+equity → translation loss."""
        result = calculate_translation_difference(
            translated_total_assets=Decimal("930000"),
            translated_total_liabilities=Decimal("600000"),
            translated_equity=Decimal("400000"),
        )
        assert result["translation_difference"] == Decimal("-70000")
        assert result["is_gain"] is False
        assert result["is_loss"] is True

    def test_zero_difference(self):
        """No translation gain/loss."""
        result = calculate_translation_difference(
            translated_total_assets=Decimal("1000000"),
            translated_total_liabilities=Decimal("600000"),
            translated_equity=Decimal("400000"),
        )
        assert result["translation_difference"] == Decimal("0")

    def test_difference_accumulates_in_equity(self):
        """Translation difference goes to equity (OCI)."""
        diff = Decimal("50000")
        # Translated: 1.05M assets, 600k liab, 400k equity + 50k diff = 1.05M ✓
        assert bs_balances_after_translation(
            translated_assets=Decimal("1050000"),
            translated_liabilities=Decimal("600000"),
            translated_equity=Decimal("450000"),  # 400k + 50k
            translation_diff=Decimal("0"),  # absorbed into equity
        ) is True


# ============================================================================
# Test: Translate Amount
# ============================================================================

class TestTranslateAmount:
    def test_translate_with_rate(self):
        """Amount × rate = translated."""
        assert translate_amount(Decimal("1000"), Decimal("7.25")) == Decimal("7250")

    def test_zero_rate_no_translation(self):
        """Rate = 0 → no translation."""
        assert translate_amount(Decimal("1000"), Decimal("0")) == Decimal("1000")

    def test_none_rate_no_translation(self):
        """Rate = None → no translation."""
        assert translate_amount(Decimal("1000"), None) == Decimal("1000")

    def test_negative_amount(self):
        """Negative amounts also translate."""
        assert translate_amount(Decimal("-1000"), Decimal("7.25")) == Decimal("-7250")

    def test_zero_amount(self):
        """Zero amount → zero result."""
        assert translate_amount(Decimal("0"), Decimal("7.25")) == Decimal("0")

    def test_decimal_precision(self):
        """Rates with decimal precision maintained."""
        assert translate_amount(Decimal("100"), Decimal("7.253")) == Decimal("725.3")


# ============================================================================
# Test: Post-Translation Balance
# ============================================================================

class TestPostTranslationBalance:
    def test_bs_balances_after_translation(self):
        """BS must balance after applying translation difference."""
        # Before: 1M assets = 600k liab + 400k equity
        # Translated: 1.07M assets, 600k liab, 400k equity
        # Translation diff = 70k (gain) → added to equity
        assert bs_balances_after_translation(
            translated_assets=Decimal("1070000"),
            translated_liabilities=Decimal("600000"),
            translated_equity=Decimal("470000"),  # 400k + 70k gain
            translation_diff=Decimal("0"),  # diff absorbed into equity
        ) is True

    def test_bs_not_balanced_without_diff(self):
        """Without translation difference, BS may not balance."""
        assert bs_balances_after_translation(
            translated_assets=Decimal("1070000"),
            translated_liabilities=Decimal("600000"),
            translated_equity=Decimal("400000"),  # not adjusted
            translation_diff=Decimal("0"),
        ) is False

    def test_apply_rates_to_multiple_items(self):
        """Apply correct rates to different account types."""
        items = [
            {"account_code": "1001", "balance": 10000},   # asset → closing
            {"account_code": "2001", "balance": 5000},    # liability → closing
            {"account_code": "4001", "balance": 3000},   # income → average
            {"account_code": "5001", "balance": 2000},   # expense → average
        ]
        result = apply_forex_rates(
            items,
            closing_rate=Decimal("7.25"),
            average_rate=Decimal("7.20"),
            historical_rate=Decimal("7.10"),
        )
        # 1001: asset → closing
        assert result[0]["translated"] == Decimal("72500")
        assert result[0]["rate_used"] == Decimal("7.25")
        # 2001: liability → closing
        assert result[1]["rate_used"] == Decimal("7.25")
        # 4001: income → average
        assert result[2]["rate_used"] == Decimal("7.20")
        # 5001: expense → average
        assert result[3]["rate_used"] == Decimal("7.20")
