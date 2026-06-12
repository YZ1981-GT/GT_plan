"""Property 1: Export-Import Round-Trip (PBT)

Property 1: 导出后未修改直接导入，逐 sheet 逐单元格一致

serialize_cell_value → deserialize_cell_value round-trip 保证：
对任意有效单元格值，序列化后再反序列化应返回相同的标准表示。

**Validates: Requirements 10.1, 10.3**

Testing framework: hypothesis
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_export.serialization import (
    deserialize_cell_value,
    parse_sheet_data,
    serialize_cell_value,
)

# ─── Hypothesis Strategies ────────────────────────────────────────────────────

COL_TYPES = ["number", "date", "text"]


@st.composite
def st_cell_value_with_type(draw: st.DrawFn) -> tuple:
    """Generate a (value, col_type) pair for round-trip testing.

    Generates values that are valid inputs for serialize_cell_value.
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
def st_workpaper_content(draw: st.DrawFn) -> dict:
    """Generate workpaper content structure for round-trip testing.

    Produces a dict of:
      {sheet_name: {columns: {col_letter: {field, type}}, start_row, rows: [...]}}
    """
    num_sheets = draw(st.integers(min_value=1, max_value=2))
    sheet_names = draw(
        st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N")),
                min_size=1,
                max_size=8,
            ),
            min_size=num_sheets,
            max_size=num_sheets,
            unique=True,
        )
    )

    content: dict = {}
    col_letters = ["A", "B", "C", "D", "E"]

    for sheet_name in sheet_names:
        num_cols = draw(st.integers(min_value=1, max_value=3))
        num_rows = draw(st.integers(min_value=1, max_value=3))

        columns: dict = {}
        col_types: list[str] = []
        for i in range(num_cols):
            col_type = draw(st.sampled_from(COL_TYPES))
            col_types.append(col_type)
            columns[col_letters[i]] = {
                "field": f"field_{i}",
                "type": col_type,
            }

        rows: list[list] = []
        for _ in range(num_rows):
            row: list = []
            for col_type in col_types:
                if col_type == "number":
                    val = draw(
                        st.one_of(
                            st.none(),
                            st.floats(
                                min_value=-1e6,
                                max_value=1e6,
                                allow_nan=False,
                                allow_infinity=False,
                            ),
                        )
                    )
                elif col_type == "date":
                    val = draw(
                        st.one_of(
                            st.none(),
                            st.dates(
                                min_value=date(2000, 1, 1),
                                max_value=date(2099, 12, 31),
                            ),
                        )
                    )
                else:
                    val = draw(
                        st.one_of(
                            st.none(),
                            st.text(min_size=1, max_size=20),
                        )
                    )
                row.append(val)
            rows.append(row)

        content[sheet_name] = {
            "columns": columns,
            "col_types": col_types,
            "rows": rows,
        }

    return content


# ─── Helper: Mock Worksheet ──────────────────────────────────────────────────


class MockCell:
    """Minimal cell mock for parse_sheet_data testing."""

    def __init__(self, value: object) -> None:
        self.value = value


class MockWorksheet:
    """Minimal worksheet mock for parse_sheet_data testing.

    Stores cells in a dict keyed by cell reference (e.g. "A1").
    """

    def __init__(self, data: dict[str, object], max_row: int) -> None:
        self._data = data
        self.max_row = max_row

    def __getitem__(self, key: str) -> MockCell:
        return MockCell(self._data.get(key))


# ─── Property 1: Export-Import Round-Trip ─────────────────────────────────────


class TestExportImportRoundTrip:
    """Property 1: 导出后未修改直接导入，逐 sheet 逐单元格一致

    **Validates: Requirements 10.1, 10.3**
    """

    @given(cell_with_type=st_cell_value_with_type())
    @settings(max_examples=5)
    def test_serialize_deserialize_roundtrip(
        self, cell_with_type: tuple
    ) -> None:
        """serialize_cell_value → deserialize_cell_value returns same canonical value.

        The round-trip property: for any valid input, serializing and then
        deserializing produces the same canonical representation.

        **Validates: Requirements 10.1, 10.3**
        """
        value, col_type = cell_with_type

        # Export: serialize
        serialized = serialize_cell_value(value, col_type)

        # Import: deserialize the serialized value
        deserialized = deserialize_cell_value(serialized, col_type)

        # Round-trip: should be identical
        assert serialized == deserialized, (
            f"Round-trip failed for value={value!r}, col_type={col_type!r}: "
            f"serialized={serialized!r} != deserialized={deserialized!r}"
        )

    @given(content=st_workpaper_content())
    @settings(max_examples=5)
    def test_full_sheet_roundtrip(self, content: dict) -> None:
        """Full sheet round-trip: export cells → build worksheet → parse back.

        For each sheet, serialize all cells, then construct a mock worksheet
        with those serialized values, then parse_sheet_data and verify each
        cell value matches the serialized output.

        **Validates: Requirements 10.1, 10.3**
        """
        col_letters = ["A", "B", "C", "D", "E"]

        for sheet_name, sheet_info in content.items():
            columns = sheet_info["columns"]
            col_types = sheet_info["col_types"]
            rows = sheet_info["rows"]
            start_row = 1

            # Step 1: Serialize all cells (export)
            serialized_rows: list[list] = []
            for row in rows:
                serialized_row: list = []
                for i, val in enumerate(row):
                    serialized_val = serialize_cell_value(val, col_types[i])
                    serialized_row.append(serialized_val)
                serialized_rows.append(serialized_row)

            # Step 2: Build mock worksheet with serialized values
            ws_data: dict[str, object] = {}
            for row_idx, row in enumerate(serialized_rows, start=start_row):
                for col_idx, val in enumerate(row):
                    cell_ref = f"{col_letters[col_idx]}{row_idx}"
                    ws_data[cell_ref] = val

            mock_ws = MockWorksheet(ws_data, max_row=len(serialized_rows))

            # Step 3: Parse (import)
            schema = {
                "dynamic_table": {
                    "columns": columns,
                    "start_row": start_row,
                }
            }
            parsed = parse_sheet_data(mock_ws, schema)
            parsed_rows = parsed["rows"]

            # Step 4: Verify round-trip consistency
            # Only non-empty rows are returned by parse_sheet_data
            expected_non_empty = [
                row
                for row_idx, row in enumerate(serialized_rows)
                if any(
                    v is not None and v != ""
                    for v in row
                )
            ]

            assert len(parsed_rows) == len(expected_non_empty), (
                f"Sheet '{sheet_name}': expected {len(expected_non_empty)} "
                f"non-empty rows, got {len(parsed_rows)}"
            )

            for row_i, (parsed_row, serialized_row) in enumerate(
                zip(parsed_rows, expected_non_empty)
            ):
                for col_i, col_letter in enumerate(
                    list(columns.keys())
                ):
                    col_def = columns[col_letter]
                    field = col_def["field"]
                    expected_val = serialized_row[col_i]
                    actual_val = parsed_row.get(field)

                    # deserialize should produce same canonical value
                    assert actual_val == expected_val, (
                        f"Sheet '{sheet_name}' row {row_i} col {col_letter}: "
                        f"expected {expected_val!r}, got {actual_val!r}"
                    )
