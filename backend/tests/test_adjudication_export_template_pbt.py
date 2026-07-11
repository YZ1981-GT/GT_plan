"""Property-Based Tests (Hypothesis) for AdjudicationExportTemplateService.

Validates: Design Properties 1, 2, 3, 4, 9, 10, 11
"""

from __future__ import annotations

import io

from hypothesis import given, settings
from hypothesis import strategies as st
from openpyxl import Workbook, load_workbook

from app.services.adjudication_export_template_service import (
    AdjudicationExportTemplateService as Svc,
)

# ── Strategies ────────────────────────────────────────────────────────────────

# Valid adjudication wp_code: letter A-N + 1-2 digits + "-1"
valid_wp_code = st.from_regex(r"\A[A-N]\d{1,2}-1\Z", fullmatch=True)

# Invalid wp_codes (patterns that should NOT match)
invalid_wp_code = st.one_of(
    st.from_regex(r"\A[O-Z]\d{1,2}-1\Z", fullmatch=True),  # Letters O-Z
    st.from_regex(r"\A[A-N]\d{1,2}-[2-9]\Z", fullmatch=True),  # Wrong suffix digit
    st.from_regex(r"\A[a-n]\d{1,2}-1\Z", fullmatch=True),  # Lowercase letters
    st.just(""),  # Empty string
)


# ══════════════════════════════════════════════════════════════════════════════
# 7.1 PBT for Property 1 — is_adjudication_table correctness
# ══════════════════════════════════════════════════════════════════════════════


class TestIsAdjudicationTableProperty:
    """**Validates: Requirements 1.1, 1.2**

    Property 1: FOR ALL wp_code matching ^[A-N]\\d+-1$, is_adjudication_table
    returns True; FOR ALL not matching, returns False.
    """

    @settings(max_examples=5)
    @given(wp_code=valid_wp_code)
    def test_accepts_valid_adjudication_codes(self, wp_code: str):
        """Valid codes (A-N + digits + -1) are always recognized."""
        assert Svc.is_adjudication_table(wp_code) is True

    @settings(max_examples=5)
    @given(wp_code=invalid_wp_code)
    def test_rejects_invalid_codes(self, wp_code: str):
        """Invalid codes (wrong letter/suffix/case/empty) are always rejected."""
        assert Svc.is_adjudication_table(wp_code) is False


# ══════════════════════════════════════════════════════════════════════════════
# 7.2 PBT for Property 4+9 — column count
# ══════════════════════════════════════════════════════════════════════════════


class TestColumnCountProperty:
    """**Validates: Requirements 3.1, 3.2, 4.2**

    Property 9: Non-aging table has exactly 12 columns.
    Property 4+9: Aging table has 12 + len(aging_headers) columns.
    """

    @settings(max_examples=5)
    @given(data=st.data())
    def test_non_aging_has_12_columns(self, data):
        """Non-aging wp_codes always produce exactly 12 header columns."""
        ws = Workbook().active
        Svc._build_multi_row_header(ws, start_col=1, aging_headers=None)

        # Column 12 (原因分析) must be present, column 13 must be empty
        assert ws.cell(2, 12).value == "原因分析"
        assert ws.cell(2, 13).value is None

    @settings(max_examples=5)
    @given(n_aging=st.integers(min_value=1, max_value=10))
    def test_aging_column_count(self, n_aging: int):
        """Aging tables have 12 + N aging columns total."""
        ws = Workbook().active
        aging_headers = [f"段{i}" for i in range(n_aging)]
        Svc._build_multi_row_header(ws, start_col=1, aging_headers=aging_headers)

        expected_total = 12 + n_aging
        # Last column (原因分析) should be at position expected_total
        assert ws.cell(2, expected_total).value == "原因分析"
        # Next column should be empty
        assert ws.cell(2, expected_total + 1).value is None


# ══════════════════════════════════════════════════════════════════════════════
# 7.3 PBT for Property 2+3 — sheet structure and header values
# ══════════════════════════════════════════════════════════════════════════════


class TestSheetStructureProperty:
    """**Validates: Requirements 2.2, 3.1, 3.2**

    Property 2: Generated workbook has 2 sheets (编制说明 + data).
    Property 3: Row 2 contains level-1 headers, Row 3 contains level-2 sub-headers.
    """

    @settings(max_examples=5)
    @given(wp_code=valid_wp_code)
    def test_header_structure_for_any_valid_code(self, wp_code: str):
        """For any valid wp_code, the data sheet has correct multi-row headers."""
        ws = Workbook().active
        Svc._build_data_sheet(ws, wp_code, "测试科目", [])

        # Row 2 level-1 headers (always present regardless of wp_code)
        assert ws.cell(2, 1).value == "项目"
        assert ws.cell(2, 2).value == "期初"
        assert ws.cell(2, 6).value == "期末"

        # Row 3 level-2 sub-headers: 期初 sub-columns
        assert ws.cell(3, 2).value == "未审"
        assert ws.cell(3, 3).value == "AJE"
        assert ws.cell(3, 4).value == "RJE"
        assert ws.cell(3, 5).value == "审定"

        # Row 3 level-2 sub-headers: 期末 sub-columns
        assert ws.cell(3, 6).value == "未审"
        assert ws.cell(3, 7).value == "AJE"
        assert ws.cell(3, 8).value == "RJE"
        assert ws.cell(3, 9).value == "审定"

    @settings(max_examples=5)
    @given(wp_code=valid_wp_code)
    def test_title_row_format(self, wp_code: str):
        """Title row always follows '{wp_name}审定表 {wp_code}' format."""
        ws = Workbook().active
        Svc._build_data_sheet(ws, wp_code, "测试科目", [])

        expected_title = f"测试科目审定表 {wp_code}"
        assert ws.cell(1, 1).value == expected_title


# ══════════════════════════════════════════════════════════════════════════════
# 7.4 PBT for Property 10+11 — merged cells correctness and xlsx validity
# ══════════════════════════════════════════════════════════════════════════════


class TestMergedCellsAndValidityProperty:
    """**Validates: Requirements 3.3, 3.4, 2.1**

    Property 10: Merged cells include expected ranges (vertical + horizontal).
    Property 11: The resulting BytesIO is a valid xlsx loadable by openpyxl.
    """

    @settings(max_examples=5)
    @given(n_aging=st.integers(min_value=0, max_value=8))
    def test_merged_cells_correctness(self, n_aging: int):
        """Core merge ranges are always present regardless of aging column count."""
        ws = Workbook().active
        aging = [f"段{i}" for i in range(n_aging)] if n_aging > 0 else None
        Svc._build_multi_row_header(ws, start_col=1, aging_headers=aging)

        merged = [str(m) for m in ws.merged_cells.ranges]

        # 项目 always vertically merged: A2:A3
        assert "A2:A3" in merged
        # 期初 always horizontally merged: B2:E2
        assert "B2:E2" in merged
        # 期末 always horizontally merged: F2:I2
        assert "F2:I2" in merged

    @settings(max_examples=5)
    @given(n_aging=st.integers(min_value=0, max_value=8))
    def test_xlsx_validity(self, n_aging: int):
        """Generated workbook is always a valid xlsx file loadable by openpyxl."""
        ws = Workbook().active
        aging = [f"段{i}" for i in range(n_aging)] if n_aging > 0 else None
        Svc._build_multi_row_header(ws, start_col=1, aging_headers=aging)

        # Save to BytesIO and reload — must not raise
        buf = io.BytesIO()
        ws.parent.save(buf)
        buf.seek(0)
        wb2 = load_workbook(buf)
        assert wb2 is not None
        assert len(wb2.sheetnames) >= 1
