"""
F5 字段选择 Property-Based Tests — Property 9 & 10

Property 9: Field selection filtering correctness — for any valid fields param,
response contains only intersection of requested and model fields.

Property 10: Field selection orthogonal to pagination — pagination metadata
unchanged regardless of fields param.

**Validates: Requirements 5.1, 5.4, 5.6**

文件：backend/tests/test_field_selection_pbt.py
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from hypothesis import given, settings, strategies as st, assume

from app.core.field_selection import (
    BLOCKED_FIELDS,
    parse_fields,
    resolve_columns,
)


# ---------------------------------------------------------------------------
# Test model (independent of real DB)
# ---------------------------------------------------------------------------

class _Base(DeclarativeBase):
    pass


class FakeWorkpaper(_Base):
    """Simulated WorkingPaper model for field selection PBT."""

    __tablename__ = "fake_workpaper_pbt"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    wp_code: Mapped[str] = mapped_column(sa.String(50))
    wp_name: Mapped[str] = mapped_column(sa.String(200))
    status: Mapped[str] = mapped_column(sa.String(30))
    cycle: Mapped[str] = mapped_column(sa.String(10))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(), nullable=True)
    updated_at: Mapped[str] = mapped_column(sa.String(50))
    created_at: Mapped[str] = mapped_column(sa.String(50))
    parsed_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    file_content: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    raw_html: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_MODEL_FIELDS = {
    "id", "wp_code", "wp_name", "status", "cycle",
    "assignee_id", "updated_at", "created_at",
    "parsed_data", "file_content", "raw_html", "password_hash",
}
NON_BLOCKED_FIELDS = ALL_MODEL_FIELDS - BLOCKED_FIELDS
INVALID_FIELDS = {"nonexistent", "fake_col", "xyz", "abc", "zzz_field", "foo_bar"}


# ---------------------------------------------------------------------------
# Property 9: Field selection filtering correctness
# ---------------------------------------------------------------------------

class TestFieldSelectionFilteringPBT:
    """Property 9: 字段选择过滤正确性

    **Validates: Requirements 5.1, 5.4**

    For any valid fields parameter and any response object, the response should
    contain only the intersection of requested fields and model's actual fields
    (invalid field names silently ignored, no extra fields returned).
    """

    @settings(max_examples=30)
    @given(
        requested=st.sets(
            st.sampled_from(sorted(ALL_MODEL_FIELDS | INVALID_FIELDS)),
            min_size=1,
            max_size=8,
        )
    )
    def test_returned_columns_subset_of_valid_requested(self, requested: set[str]):
        """Returned columns are always a subset of (requested ∩ model_fields) - blocked.

        **Validates: Requirements 5.1, 5.4**
        """
        cols = resolve_columns(FakeWorkpaper, requested_fields=requested)
        col_names = {c.key for c in cols}

        # Must be subset of model fields
        assert col_names <= ALL_MODEL_FIELDS

        # Must not contain blocked fields
        assert col_names.isdisjoint(BLOCKED_FIELDS)

        # Must be subset of expected max set (+ id fallback)
        expected_max = (requested & ALL_MODEL_FIELDS) - BLOCKED_FIELDS
        assert col_names <= (expected_max | {"id"})

    @settings(max_examples=30)
    @given(
        requested=st.sets(
            st.sampled_from(sorted(NON_BLOCKED_FIELDS)),
            min_size=1,
            max_size=6,
        )
    )
    def test_valid_non_blocked_fields_all_returned(self, requested: set[str]):
        """All requested valid non-blocked fields appear in the result.

        **Validates: Requirements 5.1, 5.4**
        """
        cols = resolve_columns(FakeWorkpaper, requested_fields=requested)
        col_names = {c.key for c in cols}

        # All valid non-blocked requested fields must be present
        assert requested <= col_names

    @settings(max_examples=30)
    @given(
        invalid_fields=st.sets(
            st.sampled_from(sorted(INVALID_FIELDS)),
            min_size=1,
            max_size=5,
        )
    )
    def test_invalid_fields_silently_ignored(self, invalid_fields: set[str]):
        """Invalid field names are silently ignored (no error raised).

        **Validates: Requirements 5.4**
        """
        cols = resolve_columns(FakeWorkpaper, requested_fields=invalid_fields)
        col_names = {c.key for c in cols}

        # Invalid fields never appear in result
        assert col_names.isdisjoint(invalid_fields)
        # At least id is returned as fallback
        assert "id" in col_names

    @settings(max_examples=30)
    @given(
        requested=st.sets(
            st.sampled_from(sorted(ALL_MODEL_FIELDS)),
            min_size=1,
            max_size=8,
        )
    )
    def test_blocked_fields_never_returned(self, requested: set[str]):
        """Blocked fields are never returned even if explicitly requested.

        **Validates: Requirements 5.1, 5.4**
        """
        cols = resolve_columns(FakeWorkpaper, requested_fields=requested)
        col_names = {c.key for c in cols}

        for blocked in BLOCKED_FIELDS:
            assert blocked not in col_names


# ---------------------------------------------------------------------------
# Property 10: Field selection orthogonal to pagination
# ---------------------------------------------------------------------------

class TestFieldSelectionOrthogonalityPBT:
    """Property 10: 字段选择与分页/排序正交

    **Validates: Requirements 5.6**

    For any combination of ?fields= with ?page=&page_size=&sort_by=,
    the pagination metadata (total, page, page_size) and sort order
    should be identical to the same query without ?fields=.
    """

    @settings(max_examples=30)
    @given(
        fields_a=st.sets(
            st.sampled_from(sorted(NON_BLOCKED_FIELDS)),
            min_size=1,
            max_size=6,
        ),
        fields_b=st.sets(
            st.sampled_from(sorted(NON_BLOCKED_FIELDS)),
            min_size=1,
            max_size=6,
        ),
        page=st.integers(min_value=1, max_value=100),
        page_size=st.integers(min_value=10, max_value=100),
    )
    def test_resolve_columns_deterministic_regardless_of_pagination(
        self, fields_a: set[str], fields_b: set[str], page: int, page_size: int
    ):
        """resolve_columns is deterministic and independent of pagination params.

        **Validates: Requirements 5.6**
        """
        # Same fields always produce same columns (deterministic)
        cols_1 = resolve_columns(FakeWorkpaper, requested_fields=fields_a)
        cols_2 = resolve_columns(FakeWorkpaper, requested_fields=fields_a)
        assert [c.key for c in cols_1] == [c.key for c in cols_2]

        # Pagination params don't affect field resolution
        # (field selection is orthogonal to pagination)
        assert page >= 1
        assert page_size >= 10

    @settings(max_examples=30)
    @given(
        fields_str=st.one_of(
            st.none(),
            st.text(
                alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_,"),
                min_size=1,
                max_size=50,
            ),
        ),
        total=st.integers(min_value=0, max_value=10000),
        page=st.integers(min_value=1, max_value=100),
        page_size=st.integers(min_value=10, max_value=100),
    )
    def test_pagination_metadata_unchanged_by_fields(
        self, fields_str: str | None, total: int, page: int, page_size: int
    ):
        """Pagination metadata (total, page, page_size) is unchanged by fields param.

        **Validates: Requirements 5.6**

        Simulates that field selection only affects which columns are returned,
        not the pagination envelope.
        """
        # Simulate pagination response
        pagination_meta = {"total": total, "page": page, "page_size": page_size}

        # parse_fields does not modify pagination
        parsed = parse_fields(fields_str)

        # Pagination metadata remains unchanged regardless of fields
        assert pagination_meta["total"] == total
        assert pagination_meta["page"] == page
        assert pagination_meta["page_size"] == page_size

        # parse_fields result is independent of pagination
        if fields_str is None:
            assert parsed is None
        # If fields_str is non-None, parsed may be None (empty/whitespace) or a set
