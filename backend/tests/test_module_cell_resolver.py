"""Tests for Module_Cell_Resolver — 跨模块单元格级查询（Req 13）

Property 24: source URI 解析 round-trip
Property 25: 模块路由 + 输出形态
4 模块 × 选区 e2e（4 条）
"""

import pytest
from hypothesis import given, settings, strategies as st, assume

from app.services.custom_query.module_cell_resolver import (
    parse_source_uri,
    format_source_uri,
    is_module_cell_source,
    _parse_cell_ranges,
    _extract_cells_from_virtual_sheet,
    _index_to_col_letter,
    _col_letter_to_index,
    ModuleCellResolver,
    _REPORT_COLUMNS,
    _NOTE_COLUMNS,
    _ADJ_COLUMNS,
    _TB_COLUMNS,
)


# ─── Strategies ──────────────────────────────────────────────────────────────

# Valid module prefixes
_MODULES = ["report", "note", "adj", "tb"]

# Valid qualifiers per module
_REPORT_TYPES = st.sampled_from([
    "balance_sheet", "income_statement", "cash_flow_statement",
    "cash_flow_supplement", "equity_statement", "impairment_provision",
])
_NOTE_SECTIONS = st.sampled_from([
    "五-1-1", "五-1-2", "五-2-1", "五-3-1", "五-4-1",
    "六-1", "六-2", "七-1", "八-1",
])
_ADJ_TYPES = st.sampled_from(["aje", "rcl", "rje"])
_TB_DIMS = st.sampled_from(["detail", "summary"])

# Valid cell range expressions
_SINGLE_COL = st.integers(min_value=1, max_value=7).map(lambda c: _index_to_col_letter(c))
_SINGLE_ROW = st.integers(min_value=1, max_value=100)
_SINGLE_CELL = st.tuples(_SINGLE_COL, _SINGLE_ROW).map(lambda t: f"{t[0]}{t[1]}")
_CELL_RANGE = st.tuples(_SINGLE_COL, _SINGLE_ROW, _SINGLE_COL, _SINGLE_ROW).map(
    lambda t: f"{t[0]}{t[1]}:{t[2]}{t[3]}"
)
_VALID_RANGE = st.one_of(_SINGLE_CELL, _CELL_RANGE)


def _st_source_uri():
    """Strategy for valid source URIs across all 5 namespaces."""
    report_uri = st.tuples(_REPORT_TYPES, _VALID_RANGE).map(lambda t: f"report:{t[0]}|{t[1]}")
    note_uri = st.tuples(_NOTE_SECTIONS, _VALID_RANGE).map(lambda t: f"note:{t[0]}|{t[1]}")
    adj_uri = st.tuples(_ADJ_TYPES, _VALID_RANGE).map(lambda t: f"adj:{t[0]}|{t[1]}")
    tb_uri = st.tuples(_TB_DIMS, _VALID_RANGE).map(lambda t: f"tb:{t[0]}|{t[1]}")
    wp_uri = st.tuples(
        st.sampled_from(["D2", "E1", "F3", "K1"]),
        st.sampled_from(["审定表D2-1", "Sheet1", "明细表"]),
        _VALID_RANGE,
    ).map(lambda t: f"workpaper:{t[0]}|{t[1]}|{t[2]}")
    return st.one_of(report_uri, note_uri, adj_uri, tb_uri, wp_uri)


# ─── Property 24: source URI 解析 round-trip ─────────────────────────────────
# Feature: advanced-query-enhancements-p1p2, Property 24: Source URI parsing round-trip


class TestProperty24SourceURIRoundTrip:
    """**Validates: Requirements 13.1**

    For any valid source URI in the 5 supported namespaces, parsing then
    re-formatting must produce the original URI string.
    """

    @settings(max_examples=20)
    @given(uri=_st_source_uri())
    def test_parse_format_roundtrip(self, uri: str):
        """parse → format produces original URI"""
        parsed = parse_source_uri(uri)
        assert parsed is not None, f"Failed to parse: {uri}"
        reconstructed = format_source_uri(parsed)
        assert reconstructed == uri, f"Round-trip failed: {uri!r} → {parsed!r} → {reconstructed!r}"

    def test_report_uri_parse(self):
        """Specific example: report:balance_sheet|C5:C10"""
        uri = "report:balance_sheet|C5:C10"
        parsed = parse_source_uri(uri)
        assert parsed == {"module": "report", "qualifier": "balance_sheet", "cell_range": "C5:C10"}
        assert format_source_uri(parsed) == uri

    def test_note_uri_parse(self):
        """Specific example: note:五-1-1|C3:D8"""
        uri = "note:五-1-1|C3:D8"
        parsed = parse_source_uri(uri)
        assert parsed == {"module": "note", "qualifier": "五-1-1", "cell_range": "C3:D8"}
        assert format_source_uri(parsed) == uri

    def test_adj_uri_parse(self):
        """Specific example: adj:aje|B2:E10"""
        uri = "adj:aje|B2:E10"
        parsed = parse_source_uri(uri)
        assert parsed == {"module": "adj", "qualifier": "aje", "cell_range": "B2:E10"}
        assert format_source_uri(parsed) == uri

    def test_tb_uri_parse(self):
        """Specific example: tb:detail|C1:C50"""
        uri = "tb:detail|C1:C50"
        parsed = parse_source_uri(uri)
        assert parsed == {"module": "tb", "qualifier": "detail", "cell_range": "C1:C50"}
        assert format_source_uri(parsed) == uri

    def test_workpaper_uri_parse(self):
        """Specific example: workpaper:D2|审定表D2-1|A1:B10"""
        uri = "workpaper:D2|审定表D2-1|A1:B10"
        parsed = parse_source_uri(uri)
        assert parsed == {"module": "workpaper", "qualifier": "D2", "sheet_name": "审定表D2-1", "cell_range": "A1:B10"}
        assert format_source_uri(parsed) == uri

    def test_invalid_uri_returns_none(self):
        """Invalid URIs return None"""
        assert parse_source_uri("") is None
        assert parse_source_uri("unknown:foo|bar") is None
        assert parse_source_uri("just_a_string") is None

    def test_is_module_cell_source(self):
        """is_module_cell_source correctly identifies 4-module cell sources"""
        assert is_module_cell_source("report:balance_sheet|C5:C10") is True
        assert is_module_cell_source("note:五-1-1|C3:D8") is True
        assert is_module_cell_source("adj:aje|B2:E10") is True
        assert is_module_cell_source("tb:detail|C1:C50") is True
        # Without cell_range → not a cell source
        assert is_module_cell_source("report:balance_sheet") is False
        # workpaper is not in the 4 modules
        assert is_module_cell_source("workpaper:D2|Sheet1|A1:B10") is False
        assert is_module_cell_source("") is False


# ─── Property 25: 模块路由 + 输出形态 ────────────────────────────────────────
# Feature: advanced-query-enhancements-p1p2, Property 25: Module cell resolver routing and output shape


class TestProperty25ModuleRoutingOutputShape:
    """**Validates: Requirements 13.2, 13.3**

    For any valid source URI, the Module_Cell_Resolver must route to the correct
    module-specific query function AND return results where every item contains
    all required fields: {cell_ref, value, formula, sheet_name, module} with
    module matching the source namespace prefix.
    """

    @settings(max_examples=20)
    @given(
        module=st.sampled_from(_MODULES),
        qualifier=st.one_of(_REPORT_TYPES, _NOTE_SECTIONS, _ADJ_TYPES, _TB_DIMS),
        cell_range=_VALID_RANGE,
    )
    def test_extract_cells_output_shape(self, module: str, qualifier: str, cell_range: str):
        """_extract_cells_from_virtual_sheet always returns correct shape"""
        # Build sample data matching the module's column structure
        columns = {
            "report": _REPORT_COLUMNS,
            "note": _NOTE_COLUMNS,
            "adj": _ADJ_COLUMNS,
            "tb": _TB_COLUMNS,
        }[module]

        # Create some sample rows
        sample_rows = []
        for i in range(5):
            row = {}
            for col in columns:
                if col in ("formula",):
                    row[col] = f"=SUM(A{i+1})" if i % 2 == 0 else None
                elif col in ("current_period_amount", "prior_period_amount", "year_end", "year_begin",
                             "debit_amount", "credit_amount", "opening_balance", "closing_balance", "audited_amount"):
                    row[col] = float(i * 100 + 50)
                else:
                    row[col] = f"val_{i}"
            sample_rows.append(row)

        sheet_name = f"{module}_{qualifier}"
        results = _extract_cells_from_virtual_sheet(sample_rows, columns, cell_range, sheet_name, module)

        # Verify output shape
        assert isinstance(results, list)
        for item in results:
            assert "cell_ref" in item, f"Missing cell_ref in {item}"
            assert "value" in item, f"Missing value in {item}"
            assert "formula" in item, f"Missing formula in {item}"
            assert "sheet_name" in item, f"Missing sheet_name in {item}"
            assert "module" in item, f"Missing module in {item}"
            # module must match
            assert item["module"] == module, f"Expected module={module}, got {item['module']}"
            # sheet_name must match
            assert item["sheet_name"] == sheet_name
            # cell_ref must be valid format (e.g. A1, B2, AA10)
            assert item["cell_ref"], "cell_ref must not be empty"
            import re
            assert re.match(r"^[A-Z]+\d+$", item["cell_ref"]), f"Invalid cell_ref: {item['cell_ref']}"

    def test_report_module_columns(self):
        """Report module uses correct column mapping"""
        rows = [
            {"row_code": "BS-001", "row_name": "资产", "current_period_amount": 100.0, "prior_period_amount": 90.0, "formula": "=SUM(C3:C5)"},
        ]
        results = _extract_cells_from_virtual_sheet(rows, _REPORT_COLUMNS, "A2:E2", "report_bs", "report")
        assert len(results) == 5
        # A2 = row_code
        assert results[0]["value"] == "BS-001"
        assert results[0]["cell_ref"] == "A2"
        # B2 = row_name
        assert results[1]["value"] == "资产"
        # C2 = current_period_amount
        assert results[2]["value"] == 100.0
        # D2 = prior_period_amount
        assert results[3]["value"] == 90.0
        # E2 = formula (column named "formula" → also appears in formula field)
        assert results[4]["value"] == "=SUM(C3:C5)"

    def test_note_module_columns(self):
        """Note module uses correct column mapping"""
        rows = [
            {"code": "1001", "name": "现金", "year_end": 100, "year_begin": 90, "formula": None},
        ]
        results = _extract_cells_from_virtual_sheet(rows, _NOTE_COLUMNS, "A2:E2", "note_五-1-1", "note")
        assert len(results) == 5
        assert results[0]["value"] == "1001"
        assert results[1]["value"] == "现金"
        assert results[2]["value"] == 100
        assert results[3]["value"] == 90
        assert results[4]["module"] == "note"

    def test_adj_module_columns(self):
        """Adj module uses correct column mapping"""
        rows = [
            {"entry_no": "AJE-001", "account_code": "1122", "account_name": "应收账款", "debit_amount": 500.0, "credit_amount": None, "description": "调整"},
        ]
        results = _extract_cells_from_virtual_sheet(rows, _ADJ_COLUMNS, "A2:F2", "adj_aje", "adj")
        assert len(results) == 6
        assert results[0]["value"] == "AJE-001"
        assert results[1]["value"] == "1122"
        assert results[2]["value"] == "应收账款"
        assert results[3]["value"] == 500.0
        assert results[4]["value"] == ""  # None → ""
        assert results[5]["value"] == "调整"

    def test_tb_module_columns(self):
        """TB module uses correct column mapping"""
        rows = [
            {"account_code": "1001", "account_name": "现金", "opening_balance": 1000.0, "debit_amount": 200.0, "credit_amount": 100.0, "closing_balance": 1100.0, "audited_amount": 1100.0},
        ]
        results = _extract_cells_from_virtual_sheet(rows, _TB_COLUMNS, "A2:G2", "tb_detail", "tb")
        assert len(results) == 7
        assert results[0]["value"] == "1001"
        assert results[1]["value"] == "现金"
        assert results[2]["value"] == 1000.0
        assert results[3]["value"] == 200.0
        assert results[4]["value"] == 100.0
        assert results[5]["value"] == 1100.0
        assert results[6]["value"] == 1100.0
        for item in results:
            assert item["module"] == "tb"

    def test_header_row_extraction(self):
        """Row 1 returns column headers"""
        rows = [{"row_code": "BS-001", "row_name": "资产", "current_period_amount": 100.0, "prior_period_amount": 90.0, "formula": None}]
        results = _extract_cells_from_virtual_sheet(rows, _REPORT_COLUMNS, "A1:E1", "report_bs", "report")
        assert len(results) == 5
        assert results[0]["value"] == "row_code"
        assert results[1]["value"] == "row_name"
        assert results[2]["value"] == "current_period_amount"
        assert results[3]["value"] == "prior_period_amount"
        assert results[4]["value"] == "formula"

    def test_out_of_bounds_returns_empty(self):
        """Cells beyond data rows return empty string"""
        rows = [{"row_code": "BS-001", "row_name": "资产", "current_period_amount": 100.0, "prior_period_amount": 90.0, "formula": None}]
        results = _extract_cells_from_virtual_sheet(rows, _REPORT_COLUMNS, "A10", "report_bs", "report")
        assert len(results) == 1
        assert results[0]["value"] == ""

    def test_max_cells_cap(self):
        """Extraction is capped at 500 cells"""
        rows = [{"row_code": f"R{i}", "row_name": f"Name{i}", "current_period_amount": i, "prior_period_amount": i, "formula": None} for i in range(600)]
        # Request a huge range
        results = _extract_cells_from_virtual_sheet(rows, _REPORT_COLUMNS, "A1:E200", "report_bs", "report")
        assert len(results) == 500


# ─── Helper function tests ───────────────────────────────────────────────────


class TestHelperFunctions:
    """Unit tests for helper functions."""

    def test_col_letter_to_index(self):
        assert _col_letter_to_index("A") == 1
        assert _col_letter_to_index("B") == 2
        assert _col_letter_to_index("Z") == 26
        assert _col_letter_to_index("AA") == 27
        assert _col_letter_to_index("AB") == 28

    def test_index_to_col_letter(self):
        assert _index_to_col_letter(1) == "A"
        assert _index_to_col_letter(2) == "B"
        assert _index_to_col_letter(26) == "Z"
        assert _index_to_col_letter(27) == "AA"
        assert _index_to_col_letter(28) == "AB"

    @settings(max_examples=20)
    @given(idx=st.integers(min_value=1, max_value=702))
    def test_col_index_roundtrip(self, idx: int):
        """col index → letter → index round-trip"""
        letter = _index_to_col_letter(idx)
        assert _col_letter_to_index(letter) == idx

    def test_parse_cell_ranges_single(self):
        assert _parse_cell_ranges("B5") == [(5, 2, 5, 2)]

    def test_parse_cell_ranges_rect(self):
        assert _parse_cell_ranges("A1:C3") == [(1, 1, 3, 3)]

    def test_parse_cell_ranges_multi(self):
        assert _parse_cell_ranges("A1:A10,C1:C5") == [(1, 1, 10, 1), (1, 3, 5, 3)]

    def test_parse_cell_ranges_whole_col(self):
        result = _parse_cell_ranges("A:A")
        assert result == [(1, 1, 100, 1)]

    def test_parse_cell_ranges_empty(self):
        assert _parse_cell_ranges("") == []
        assert _parse_cell_ranges("invalid") == []


# ─── 4 模块 × 选区 e2e（模拟 DB 交互）────────────────────────────────────────


class TestModuleCellResolverE2E:
    """E2E tests for 4 module cell queries (mocked DB)."""

    @pytest.fixture
    def resolver(self):
        return ModuleCellResolver()

    @pytest.mark.asyncio
    async def test_resolve_report_no_project(self, resolver):
        """Report query without project_id returns error"""
        from unittest.mock import AsyncMock
        db = AsyncMock()
        result = await resolver.resolve(db, "report:balance_sheet|C2:C5", None, 2025)
        assert result["total"] == 0
        assert "error" in result

    @pytest.mark.asyncio
    async def test_resolve_invalid_source(self, resolver):
        """Invalid source returns error"""
        from unittest.mock import AsyncMock
        db = AsyncMock()
        result = await resolver.resolve(db, "unknown:foo|bar", "proj-1", 2025)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_resolve_no_cell_range(self, resolver):
        """Source without cell_range returns error"""
        from unittest.mock import AsyncMock
        db = AsyncMock()
        result = await resolver.resolve(db, "report:balance_sheet", "proj-1", 2025)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_resolve_report_with_data(self, resolver):
        """Report module returns correct data from mocked DB"""
        from unittest.mock import AsyncMock, MagicMock

        # Mock DB response
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: {
            0: {
                "rows": [
                    {"row_code": "BS-001", "row_name": "货币资金", "current_period_amount": 12345.67, "prior_period_amount": 11000.0, "formula": "=tb:1001+tb:1002"},
                    {"row_code": "BS-002", "row_name": "应收账款", "current_period_amount": 5000.0, "prior_period_amount": 4500.0, "formula": None},
                ]
            }
        }[idx]

        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await resolver.resolve(db, "report:balance_sheet|C2:C3", "proj-1", 2025)
        assert result["module"] == "report"
        assert result["source"] == "jsonb_direct"
        assert result["total"] == 2
        # C2 = current_period_amount of first row
        assert result["rows"][0]["cell_ref"] == "C2"
        assert result["rows"][0]["value"] == 12345.67
        assert result["rows"][0]["module"] == "report"
        # C3 = current_period_amount of second row
        assert result["rows"][1]["cell_ref"] == "C3"
        assert result["rows"][1]["value"] == 5000.0

    @pytest.mark.asyncio
    async def test_resolve_note_with_data(self, resolver):
        """Note module returns correct data from mocked DB"""
        from unittest.mock import AsyncMock, MagicMock

        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: {
            0: {
                "rows": [
                    {"code": "1001", "name": "现金", "year_end": 100, "year_begin": 90, "formula": None},
                ]
            }
        }[idx]

        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await resolver.resolve(db, "note:五-1-1|A2:E2", "proj-1", 2025)
        assert result["module"] == "note"
        assert result["total"] == 5
        assert result["rows"][0]["value"] == "1001"
        assert result["rows"][1]["value"] == "现金"
        assert result["rows"][2]["value"] == 100
        assert result["rows"][3]["value"] == 90
        for item in result["rows"]:
            assert item["module"] == "note"

    @pytest.mark.asyncio
    async def test_resolve_adj_with_data(self, resolver):
        """Adj module returns correct data from mocked DB"""
        from unittest.mock import AsyncMock, MagicMock

        # adjustments query returns tuples
        mock_rows = [
            ("AJE-001", "1122", "应收账款", 500.0, None, "调整应收"),
            ("AJE-002", "2202", "应付账款", None, 300.0, "调整应付"),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await resolver.resolve(db, "adj:aje|A2:F3", "proj-1", 2025)
        assert result["module"] == "adj"
        assert result["total"] == 12  # 2 rows × 6 cols
        # First row data
        assert result["rows"][0]["cell_ref"] == "A2"
        assert result["rows"][0]["value"] == "AJE-001"
        assert result["rows"][5]["cell_ref"] == "F2"
        assert result["rows"][5]["value"] == "调整应收"
        for item in result["rows"]:
            assert item["module"] == "adj"

    @pytest.mark.asyncio
    async def test_resolve_tb_with_data(self, resolver):
        """TB module returns correct data from mocked DB"""
        from unittest.mock import AsyncMock, MagicMock

        mock_rows = [
            ("1001", "现金", 1000.0, 200.0, 0, 1200.0, 1200.0),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await resolver.resolve(db, "tb:detail|A2:G2", "proj-1", 2025)
        assert result["module"] == "tb"
        assert result["total"] == 7
        assert result["rows"][0]["value"] == "1001"
        assert result["rows"][1]["value"] == "现金"
        assert result["rows"][2]["value"] == 1000.0
        assert result["rows"][6]["value"] == 1200.0
        for item in result["rows"]:
            assert item["module"] == "tb"
