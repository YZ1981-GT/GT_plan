"""Property-Based Tests for A13 Communication Draft.

Tests draft filtering/completeness and template selection using hypothesis.

Feature: a13-misstatement-aggregation
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.a13_communication_draft import (
    build_draft_items,
    generate_communication_draft,
    select_template,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════════════════════

MISSTATEMENT_TYPES = ["factual", "judgmental", "projected"]
PRIOR_YEAR_STATUSES = ["new", "continuing", "reversed"]


def misstatement_row_strategy():
    """Generate a single misstatement row dict with all required fields."""
    return st.fixed_dictionaries({
        "misstatement_description": st.text(min_size=1, max_size=50),
        "affected_account_code": st.text(min_size=1, max_size=10),
        "affected_account_name": st.text(min_size=1, max_size=30),
        "misstatement_amount": st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("99999999.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        "misstatement_type": st.sampled_from(MISSTATEMENT_TYPES),
        "management_reason": st.text(min_size=0, max_size=50),
        "prior_year_status": st.sampled_from(PRIOR_YEAR_STATUSES),
    })


def misstatement_list_strategy(min_size=0, max_size=20):
    """Generate a list of misstatement rows."""
    return st.lists(misstatement_row_strategy(), min_size=min_size, max_size=max_size)


def positive_decimal_strategy(max_value=Decimal("999999999.99")):
    """Generate positive decimal amounts."""
    return st.decimals(
        min_value=Decimal("0.01"),
        max_value=max_value,
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 8: Communication draft filtering and completeness
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty8CommunicationDraftFiltering:
    """Property 8: Communication draft filtering and completeness.

    *For any* set of misstatements with mixed prior_year_status values, the generated
    Communication_Draft SHALL include exactly those items where
    prior_year_status IN ('continuing', 'new'), and each item SHALL contain all
    required fields.

    **Validates: Requirements 5.1, 5.2, 5.3**
    """

    @settings(max_examples=100, deadline=None)
    @given(rows=misstatement_list_strategy(min_size=1, max_size=30))
    def test_only_continuing_and_new_included(self, rows):
        """Draft items only include records with status 'continuing' or 'new'."""
        items = build_draft_items(rows)
        expected_count = sum(
            1 for r in rows if r["prior_year_status"] in ("continuing", "new")
        )
        assert len(items) == expected_count

    @settings(max_examples=100, deadline=None)
    @given(rows=misstatement_list_strategy(min_size=1, max_size=20))
    def test_reversed_excluded(self, rows):
        """Reversed records are never included in draft items."""
        # Force at least one reversed
        rows[0] = {**rows[0], "prior_year_status": "reversed"}
        items = build_draft_items(rows)
        # Count non-reversed
        non_reversed = sum(
            1 for r in rows if r["prior_year_status"] != "reversed"
        )
        assert len(items) == non_reversed

    @settings(max_examples=100, deadline=None)
    @given(rows=misstatement_list_strategy(min_size=1, max_size=20))
    def test_each_item_has_required_fields(self, rows):
        """Each item in the draft contains all required fields."""
        items = build_draft_items(rows)
        required_fields = {
            "seq", "description", "affected_account", "amount",
            "misstatement_type", "management_reason"
        }
        for item in items:
            assert required_fields.issubset(set(item.keys())), (
                f"Missing fields: {required_fields - set(item.keys())}"
            )

    @settings(max_examples=100, deadline=None)
    @given(rows=misstatement_list_strategy(min_size=1, max_size=20))
    def test_seq_numbers_sequential(self, rows):
        """Sequence numbers are 1-based and sequential."""
        items = build_draft_items(rows)
        for i, item in enumerate(items):
            assert item["seq"] == i + 1

    @settings(max_examples=100, deadline=None)
    @given(rows=misstatement_list_strategy(min_size=0, max_size=5))
    def test_empty_rows_returns_empty_draft(self, rows):
        """When all rows are reversed or empty, draft is flagged as empty."""
        # Make all rows reversed
        reversed_rows = [{**r, "prior_year_status": "reversed"} for r in rows]
        draft = generate_communication_draft(reversed_rows, Decimal("5000000"))
        if not rows:
            assert draft.get("_empty") is True
        else:
            assert draft.get("_empty") is True

    @settings(max_examples=100, deadline=None)
    @given(rows=misstatement_list_strategy(min_size=1, max_size=10))
    def test_non_empty_draft_has_format_field(self, rows):
        """Non-empty draft has _format = 'communication-draft-v1'."""
        # Ensure at least one non-reversed
        rows[0] = {**rows[0], "prior_year_status": "new"}
        draft = generate_communication_draft(rows, Decimal("5000000"))
        assert draft.get("_format") == "communication-draft-v1"
        assert "items" in draft
        assert "summary" in draft
        assert "conclusion_text" in draft


# ═══════════════════════════════════════════════════════════════════════════════
# Property 9: Communication draft template selection
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty9TemplateSelection:
    """Property 9: Communication draft template selection.

    *For any* (cumulative_amount, pm) pair where pm > 0:
    - Template A when cumulative < pm * 0.75 (below PM)
    - Template B when pm * 0.75 <= cumulative < pm (approaching PM)
    - Template C when cumulative >= pm (exceeds PM)

    **Validates: Requirements 5.6**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        pm=st.decimals(
            min_value=Decimal("1000"),
            max_value=Decimal("100000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        fraction=st.floats(min_value=0.01, max_value=0.74),
    )
    def test_template_a_below_75_percent(self, pm, fraction):
        """Template A when cumulative < PM * 0.75."""
        cumulative = (pm * Decimal(str(fraction))).quantize(Decimal("0.01"))
        assume(cumulative < pm * Decimal("0.75"))
        result = select_template(cumulative, pm)
        assert result == "A"

    @settings(max_examples=100, deadline=None)
    @given(
        pm=st.decimals(
            min_value=Decimal("1000"),
            max_value=Decimal("100000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        fraction=st.floats(min_value=0.75, max_value=0.99),
    )
    def test_template_b_between_75_and_100_percent(self, pm, fraction):
        """Template B when PM * 0.75 <= cumulative < PM."""
        cumulative = (pm * Decimal(str(fraction))).quantize(Decimal("0.01"))
        assume(cumulative >= pm * Decimal("0.75"))
        assume(cumulative < pm)
        result = select_template(cumulative, pm)
        assert result == "B"

    @settings(max_examples=100, deadline=None)
    @given(
        pm=st.decimals(
            min_value=Decimal("100"),
            max_value=Decimal("100000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        extra=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("100000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_template_c_at_or_above_pm(self, pm, extra):
        """Template C when cumulative >= PM."""
        cumulative = pm + extra
        result = select_template(cumulative, pm)
        assert result == "C"

    @settings(max_examples=100, deadline=None)
    @given(cumulative=positive_decimal_strategy())
    def test_template_a_when_pm_none(self, cumulative):
        """Default to template A when PM is None."""
        result = select_template(cumulative, None)
        assert result == "A"

    @settings(max_examples=100, deadline=None)
    @given(cumulative=positive_decimal_strategy())
    def test_template_a_when_pm_zero(self, cumulative):
        """Default to template A when PM is 0."""
        result = select_template(cumulative, Decimal("0"))
        assert result == "A"
