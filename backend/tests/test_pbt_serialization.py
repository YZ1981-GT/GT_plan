"""Property 3 & 5: Snapshot Hash Determinism + Deterministic Serialization (PBT)

Property 3: 同内容多次哈希结果相同；不同内容哈希不同
Property 5: 同内容两次独立序列化产生 byte-identical 单元格值

**Validates: Requirements 1.5, 4.1, 10.2**

Testing framework: hypothesis
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.services.wp_export.serialization import (
    compute_snapshot_hash,
    serialize_cell_value,
)

# ─── Hypothesis Strategies ────────────────────────────────────────────────────

# Strategy: cell value with col_type
COL_TYPES = ["number", "date", "text"]


@st.composite
def st_cell_value_with_type(draw: st.DrawFn) -> tuple:
    """Generate a (value, col_type) pair for serialize_cell_value.

    Returns a tuple of (raw_value, col_type) where raw_value is appropriate
    for the selected col_type.
    """
    col_type = draw(st.sampled_from(COL_TYPES))

    if col_type == "number":
        value = draw(
            st.one_of(
                st.none(),
                st.integers(min_value=-999999999, max_value=999999999),
                st.floats(
                    min_value=-1e12,
                    max_value=1e12,
                    allow_nan=False,
                    allow_infinity=False,
                ),
                st.decimals(
                    min_value=Decimal("-999999999"),
                    max_value=Decimal("999999999"),
                    allow_nan=False,
                    allow_infinity=False,
                ),
            )
        )
    elif col_type == "date":
        value = draw(
            st.one_of(
                st.none(),
                st.dates(
                    min_value=date(2000, 1, 1),
                    max_value=date(2099, 12, 31),
                ),
                st.text(min_size=0, max_size=20),
            )
        )
    else:  # text
        value = draw(
            st.one_of(
                st.none(),
                st.text(min_size=0, max_size=50),
            )
        )

    return (value, col_type)


@st.composite
def st_workbook_data(draw: st.DrawFn) -> dict[str, list[list]]:
    """Generate workbook_data: dict of sheet_name -> list of rows.

    Each row is a list of serialized cell values (already processed through
    serialize_cell_value to match compute_snapshot_hash input contract).
    """
    num_sheets = draw(st.integers(min_value=1, max_value=3))
    sheet_names = draw(
        st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N")),
                min_size=1,
                max_size=10,
            ),
            min_size=num_sheets,
            max_size=num_sheets,
            unique=True,
        )
    )

    workbook_data: dict[str, list[list]] = {}
    for name in sheet_names:
        num_rows = draw(st.integers(min_value=1, max_value=4))
        num_cols = draw(st.integers(min_value=1, max_value=4))
        rows = []
        for _ in range(num_rows):
            row = []
            for _ in range(num_cols):
                # Generate already-serialized values (what compute_snapshot_hash expects)
                cell = draw(
                    st.one_of(
                        st.none(),
                        st.integers(min_value=-9999, max_value=9999),
                        st.floats(
                            min_value=-1e6,
                            max_value=1e6,
                            allow_nan=False,
                            allow_infinity=False,
                        ),
                        st.text(min_size=0, max_size=20),
                    )
                )
                row.append(cell)
            rows.append(row)
        workbook_data[name] = rows

    return workbook_data


# ─── Property 3: Snapshot Hash Determinism ────────────────────────────────────


class TestSnapshotHashDeterminism:
    """Property 3: 同内容多次哈希结果相同；不同内容哈希不同

    **Validates: Requirements 1.5, 4.1**
    """

    @given(workbook_data=st_workbook_data())
    @settings(max_examples=5)
    def test_same_content_same_hash(
        self, workbook_data: dict[str, list[list]]
    ) -> None:
        """Same content hashed twice produces identical result.

        **Validates: Requirements 1.5, 4.1**
        """
        hash1 = compute_snapshot_hash(workbook_data)
        hash2 = compute_snapshot_hash(workbook_data)

        assert hash1 == hash2, (
            f"Same content produced different hashes: {hash1} != {hash2}"
        )
        # SHA-256 produces 64-char hex string
        assert len(hash1) == 64
        assert all(c in "0123456789abcdef" for c in hash1)

    @given(
        workbook_data=st_workbook_data(),
        extra_value=st.text(min_size=1, max_size=10),
    )
    @settings(max_examples=5)
    def test_different_content_different_hash(
        self,
        workbook_data: dict[str, list[list]],
        extra_value: str,
    ) -> None:
        """Different content produces different hash (with high probability).

        We mutate the workbook_data by adding a new sheet with distinct content,
        ensuring the two inputs are genuinely different.

        **Validates: Requirements 1.5, 4.1**
        """
        hash_original = compute_snapshot_hash(workbook_data)

        # Create modified copy: add a new sheet that doesn't exist
        modified = dict(workbook_data)
        new_sheet_name = f"__extra_sheet_{extra_value}"
        # Ensure the new sheet name doesn't collide
        assume(new_sheet_name not in workbook_data)
        modified[new_sheet_name] = [[extra_value]]

        hash_modified = compute_snapshot_hash(modified)

        assert hash_original != hash_modified, (
            "Different content produced same hash — collision detected"
        )


# ─── Property 5: Deterministic Serialization ──────────────────────────────────


class TestDeterministicSerialization:
    """Property 5: 同内容两次独立序列化产生 byte-identical 单元格值

    **Validates: Requirements 10.2**
    """

    @given(cell_with_type=st_cell_value_with_type())
    @settings(max_examples=5)
    def test_serialize_cell_value_deterministic(
        self, cell_with_type: tuple
    ) -> None:
        """Same value serialized twice produces identical result.

        **Validates: Requirements 10.2**
        """
        value, col_type = cell_with_type

        result1 = serialize_cell_value(value, col_type)
        result2 = serialize_cell_value(value, col_type)

        assert result1 == result2, (
            f"serialize_cell_value({value!r}, {col_type!r}) not deterministic: "
            f"{result1!r} != {result2!r}"
        )
        # Additionally verify type stability
        assert type(result1) is type(result2)
