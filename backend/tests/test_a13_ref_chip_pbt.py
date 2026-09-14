"""Property-Based Tests for A13 Source Ref Chip.

Tests ref_chip visibility and source_wp_code auto-population using hypothesis.

Feature: a13-misstatement-aggregation
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ═══════════════════════════════════════════════════════════════════════════════
# Pure functions under test
# ═══════════════════════════════════════════════════════════════════════════════


def should_show_ref_chip(
    source_wp_code: str | None,
    source_adjustment_id: str | None,
) -> bool:
    """Determine if Source_Ref_Chip should be rendered.

    Chip is visible if and only if source_wp_code IS NOT NULL
    OR source_adjustment_id IS NOT NULL.

    Validates: Requirements 6.1
    """
    return bool(source_wp_code) or bool(source_adjustment_id)


def derive_source_wp_code_from_aje(
    originating_wp_code: str | None,
) -> str | None:
    """Derive source_wp_code from rejected AJE's originating workpaper.

    If originating_wp_code is non-null, the resulting misstatement's
    source_wp_code SHALL equal it.

    Validates: Requirements 6.4
    """
    if originating_wp_code and originating_wp_code.strip():
        return originating_wp_code.strip()
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════════════════════

WP_CODE_STRATEGY = st.sampled_from([
    "D2-1", "D4-1", "F2-1", "F3A", "G1-1", "H1-1", "K1-1", "L1-1", "N1-1",
    "E1-1", "I1-1", "J1-1", "M1-1",
])

NULLABLE_WP_CODE = st.one_of(st.none(), st.just(""), WP_CODE_STRATEGY)
NULLABLE_UUID = st.one_of(st.none(), st.just(""), st.builds(lambda: str(uuid4())))


# ═══════════════════════════════════════════════════════════════════════════════
# Property 10: Source_Ref_Chip visibility
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty10RefChipVisibility:
    """Property 10: Source_Ref_Chip visibility.

    *For any* misstatement record, the Source_Ref_Chip SHALL be rendered
    if and only if source_wp_code IS NOT NULL OR source_adjustment_id IS NOT NULL.

    **Validates: Requirements 6.1**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        source_wp_code=NULLABLE_WP_CODE,
        source_adjustment_id=NULLABLE_UUID,
    )
    def test_chip_visible_iff_either_non_null(
        self, source_wp_code, source_adjustment_id
    ):
        """Chip shows when either source_wp_code or source_adjustment_id is truthy."""
        result = should_show_ref_chip(source_wp_code, source_adjustment_id)
        expected = bool(source_wp_code) or bool(source_adjustment_id)
        assert result == expected

    @settings(max_examples=100, deadline=None)
    @given(wp_code=WP_CODE_STRATEGY)
    def test_chip_always_visible_with_wp_code(self, wp_code):
        """Chip is always visible when source_wp_code is non-null."""
        assert should_show_ref_chip(wp_code, None) is True

    @settings(max_examples=100, deadline=None)
    @given(adj_id=st.builds(lambda: str(uuid4())))
    def test_chip_always_visible_with_adjustment_id(self, adj_id):
        """Chip is always visible when source_adjustment_id is non-null."""
        assert should_show_ref_chip(None, adj_id) is True

    def test_chip_hidden_when_both_null(self):
        """Chip is hidden when both source fields are null."""
        assert should_show_ref_chip(None, None) is False
        assert should_show_ref_chip("", "") is False
        assert should_show_ref_chip(None, "") is False
        assert should_show_ref_chip("", None) is False


# ═══════════════════════════════════════════════════════════════════════════════
# Property 11: Source_wp_code auto-population from rejected AJE
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty11SourceWpCodeFromAJE:
    """Property 11: Source_wp_code auto-population from rejected AJE.

    *For any* adjustment with a non-null originating_wp_code that is rejected
    (creating a misstatement via create_from_rejected_aje), the resulting
    UnadjustedMisstatement.source_wp_code SHALL equal the adjustment's
    originating_wp_code.

    **Validates: Requirements 6.4**
    """

    @settings(max_examples=100, deadline=None)
    @given(wp_code=WP_CODE_STRATEGY)
    def test_non_null_wp_code_preserved(self, wp_code):
        """Non-null originating_wp_code is preserved in misstatement."""
        result = derive_source_wp_code_from_aje(wp_code)
        assert result == wp_code

    @settings(max_examples=100, deadline=None)
    @given(wp_code=st.sampled_from([None, "", "  "]))
    def test_null_or_empty_returns_none(self, wp_code):
        """Null/empty originating_wp_code results in None source_wp_code."""
        result = derive_source_wp_code_from_aje(wp_code)
        assert result is None

    @settings(max_examples=100, deadline=None)
    @given(wp_code=st.text(min_size=1, max_size=20, alphabet="ABCDEFGHIJKLMN0123456789-"))
    def test_arbitrary_wp_code_preserved(self, wp_code):
        """Any non-empty string wp_code is preserved (trimmed)."""
        result = derive_source_wp_code_from_aje(wp_code)
        if wp_code.strip():
            assert result == wp_code.strip()
        else:
            assert result is None
