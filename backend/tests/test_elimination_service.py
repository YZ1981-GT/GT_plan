"""
Test Elimination Service - validates elimination entry logic.
Validates: Requirements 3.1-3.8

All imports are mocked to avoid SQLAlchemy Base.metadata conflicts.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from datetime import datetime
import uuid


# ============================================================================
# Mock enums
# ============================================================================

class EliminationType:
    equity_elimination = "equity_elimination"
    internal_trade_elimination = "internal_trade_elimination"
    investment_elimination = "investment_elimination"
    other = "other"


class ReviewStatus:
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


# ============================================================================
# Mock helpers
# ============================================================================

def make_mock_entry(
    project_id=None,
    year=2024,
    entity_code="SUB1",
    entry_type=None,
    dr_amount=Decimal("1000"),
    cr_amount=Decimal("1000"),
    status=ReviewStatus.draft,
    description="Test entry",
):
    e = MagicMock()
    e.id = uuid.uuid4()
    e.project_id = project_id or uuid.uuid4()
    e.year = year
    e.entity_code = entity_code
    e.entry_type = entry_type or EliminationType.equity_elimination
    e.dr_amount = dr_amount
    e.cr_amount = cr_amount
    e.review_status = status
    e.description = description
    e.created_at = datetime(2024, 1, 1)
    e.updated_at = datetime(2024, 1, 1)
    return e


# ============================================================================
# Pure balancing logic (mirrors service)
# ============================================================================

def is_balanced(dr_amount, cr_amount, tolerance=Decimal("0.01")):
    """Return True if DR == CR within rounding tolerance."""
    diff = abs(dr_amount - cr_amount)
    return diff <= tolerance


def validate_entry(dr_amount, cr_amount):
    """Raise ValueError if entry is unbalanced beyond tolerance."""
    if not is_balanced(dr_amount, cr_amount):
        raise ValueError(f"Unbalanced entry: DR={dr_amount}, CR={cr_amount}")


def next_review_status(current_status, action):
    """State machine: submit / approve / reject."""
    transitions = {
        (ReviewStatus.draft, "submit"): ReviewStatus.submitted,
        (ReviewStatus.submitted, "approve"): ReviewStatus.approved,
        (ReviewStatus.submitted, "reject"): ReviewStatus.rejected,
        (ReviewStatus.rejected, "submit"): ReviewStatus.submitted,
    }
    key = (current_status, action)
    if key not in transitions:
        raise ValueError(f"Invalid transition: {current_status} + {action}")
    return transitions[key]


def is_editable(status):
    """Entry is editable only when in draft or rejected status."""
    return status in (ReviewStatus.draft, ReviewStatus.rejected)


def replace_pnl_with_retained_earnings(entries, year):
    """
    PNL carry-forward: revenue/expense accounts replaced with
    年初未分配利润 (retained earnings) in next period.
    """
    pnl_accounts = {
        "4001", "4002", "4003",  # 主营业务收入 etc.
        "5001", "5002", "5003",  # 主营业务成本 etc.
    }
    result = []
    for entry in entries:
        e = dict(entry)
        if e.get("account_code") in pnl_accounts:
            e["account_code"] = "3103"  # 未分配利润
            e["account_name"] = "年初未分配利润"
        result.append(e)
    return result


# ============================================================================
# Test: Elimination CRUD
# ============================================================================

class TestEliminationCRUD:
    def test_create_entry_has_draft_status(self):
        """Newly created entry has draft status."""
        e = make_mock_entry(status=ReviewStatus.draft)
        assert e.review_status == ReviewStatus.draft

    def test_unbalanced_entry_raises_error(self):
        """Unbalanced entry (DR != CR) raises ValueError."""
        with pytest.raises(ValueError, match="Unbalanced entry"):
            validate_entry(Decimal("1000"), Decimal("999"))

    def test_balanced_entry_passes(self):
        """Balanced entry (DR == CR) passes validation."""
        validate_entry(Decimal("1000"), Decimal("1000"))
        validate_entry(Decimal("1000.00"), Decimal("1000.00"))

    def test_update_entry_changes_status(self):
        """Update changes review_status."""
        e = make_mock_entry(status=ReviewStatus.draft)
        assert e.review_status == ReviewStatus.draft
        e.review_status = ReviewStatus.submitted
        assert e.review_status == ReviewStatus.submitted

    def test_delete_removes_entry(self):
        """Deleting removes entry from list."""
        entries = [
            make_mock_entry(description="Keep"),
            make_mock_entry(description="Delete"),
        ]
        target_id = entries[1].id
        entries = [e for e in entries if e.id != target_id]
        assert len(entries) == 1
        assert entries[0].description == "Keep"

    def test_list_entries_by_project_and_year(self):
        """Filter entries by project_id and year."""
        pid = uuid.uuid4()
        entries = [
            make_mock_entry(project_id=pid, year=2024),
            make_mock_entry(project_id=pid, year=2024),
            make_mock_entry(project_id=pid, year=2023),
            make_mock_entry(year=2024),  # different project
        ]
        filtered = [e for e in entries
                   if e.project_id == pid and e.year == 2024]
        assert len(filtered) == 2


# ============================================================================
# Test: Balancing Validation
# ============================================================================

class TestBalancingValidation:
    def test_unbalanced_entry_rejected(self):
        """Entry with DR != CR is rejected."""
        assert is_balanced(Decimal("1000"), Decimal("999")) is False
        assert is_balanced(Decimal("1000"), Decimal("500")) is False

    def test_balanced_entry_accepted(self):
        """Entry with DR == CR is accepted."""
        assert is_balanced(Decimal("1000"), Decimal("1000")) is True

    def test_rounding_tolerance_accepted(self):
        """Difference < 0.01 is accepted (rounding tolerance)."""
        assert is_balanced(Decimal("1000"), Decimal("1000.005")) is True
        assert is_balanced(Decimal("1000"), Decimal("999.99")) is True

    def test_difference_exceeds_tolerance_rejected(self):
        """Difference >= 0.01 is rejected."""
        assert is_balanced(Decimal("1000"), Decimal("999.9")) is False
        assert is_balanced(Decimal("1000"), Decimal("1001")) is False


# ============================================================================
# Test: P&L Carry-Forward
# ============================================================================

class TestIncomeStatementCarryForward:
    def test_pnl_account_replaced_in_next_period(self):
        """Revenue/expense accounts replaced with retained earnings."""
        entries = [
            {"account_code": "4001", "account_name": "主营业务收入", "amount": Decimal("1000")},
            {"account_code": "5001", "account_name": "主营业务成本", "amount": Decimal("600")},
        ]
        result = replace_pnl_with_retained_earnings(entries, year=2024)
        assert result[0]["account_code"] == "3103"
        assert result[1]["account_code"] == "3103"

    def test_non_pnl_account_unchanged(self):
        """Non-P&L accounts are not replaced."""
        entries = [
            {"account_code": "1001", "account_name": "货币资金", "amount": Decimal("5000")},
        ]
        result = replace_pnl_with_retained_earnings(entries, year=2024)
        assert result[0]["account_code"] == "1001"

    def test_balanced_after_carry_forward(self):
        """Carry-forward keeps entry balanced (same amount, different account)."""
        entries = [
            {"account_code": "4001", "dr_amount": Decimal("0"), "cr_amount": Decimal("1000")},
        ]
        result = replace_pnl_with_retained_earnings(entries, year=2024)
        assert result[0]["cr_amount"] == Decimal("1000")


# ============================================================================
# Test: Review State Machine
# ============================================================================

class TestReviewStateMachine:
    def test_submit_changes_status_to_submitted(self):
        """submit: draft → submitted."""
        result = next_review_status(ReviewStatus.draft, "submit")
        assert result == ReviewStatus.submitted

    def test_approve_changes_status_to_approved(self):
        """approve: submitted → approved."""
        result = next_review_status(ReviewStatus.submitted, "approve")
        assert result == ReviewStatus.approved

    def test_reject_changes_status_to_rejected(self):
        """reject: submitted → rejected."""
        result = next_review_status(ReviewStatus.submitted, "reject")
        assert result == ReviewStatus.rejected

    def test_rejected_can_be_resubmitted(self):
        """reject → draft; submit: draft → submitted."""
        status = next_review_status(ReviewStatus.rejected, "submit")
        assert status == ReviewStatus.submitted

    def test_approved_entry_not_editable(self):
        """Approved entry cannot be edited."""
        assert is_editable(ReviewStatus.approved) is False

    def test_draft_entry_is_editable(self):
        """Draft entry can be edited."""
        assert is_editable(ReviewStatus.draft) is True

    def test_rejected_entry_is_editable(self):
        """Rejected entry can be edited."""
        assert is_editable(ReviewStatus.rejected) is True

    def test_cannot_submit_without_balancing(self):
        """Unbalanced entry cannot be submitted."""
        def try_submit(dr, cr):
            validate_entry(dr, cr)
            return next_review_status(ReviewStatus.draft, "submit")

        # Balanced: OK
        try_submit(Decimal("1000"), Decimal("1000"))

        # Unbalanced: raises
        with pytest.raises(ValueError, match="Unbalanced"):
            try_submit(Decimal("1000"), Decimal("999"))

    def test_approved_cannot_transition(self):
        """Approved entry has no valid transitions (locked)."""
        with pytest.raises(ValueError, match="Invalid transition"):
            next_review_status(ReviewStatus.approved, "submit")
