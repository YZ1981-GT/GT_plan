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

        # 3.2 起 _query_note_cells 用 ORM select 并把 project_id 规整为 UUID，
        # 故此处须传合法 UUID（生产中 project_id 恒为真实 UUID）。
        result = await resolver.resolve(db, "note:五-1-1|A2:E2", "11111111-1111-1111-1111-111111111111", 2025)
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


class TestNoteNodeKeyWiring:
    """Task 3.1：filters.node_key 一路透传 _dispatch → resolve → _query_note_cells。

    本任务只验证「接线到位」——node_key 确实流到附注取数器的参数上。
    按 node_key 过滤 SQL 本身（有键精确等值、无键 NULL、稳定排序）由 3.2 实现并测试。
    """

    @pytest.fixture
    def resolver(self):
        return ModuleCellResolver()

    @pytest.mark.asyncio
    async def test_resolve_passes_node_key_to_note_fetcher(self, resolver, monkeypatch):
        """resolve(..., filters={node_key}) 把 node_key 传给 _query_note_cells。"""
        from unittest.mock import AsyncMock
        import app.services.custom_query.module_cell_resolver as mcr

        captured = {}

        async def _spy(db, project_id, year, section_id, cell_range, node_key=None):
            captured["project_id"] = project_id
            captured["year"] = year
            captured["section_id"] = section_id
            captured["cell_range"] = cell_range
            captured["node_key"] = node_key
            return []

        monkeypatch.setattr(mcr, "_query_note_cells", _spy)

        db = AsyncMock()
        await resolver.resolve(
            db, "note:五-1-1|A2:E2", "proj-1", 2025,
            {"node_key": "C001:consol"},
        )

        assert captured["node_key"] == "C001:consol"
        assert captured["project_id"] == "proj-1"
        assert captured["year"] == 2025
        assert captured["section_id"] == "五-1-1"
        assert captured["cell_range"] == "A2:E2"

    @pytest.mark.asyncio
    async def test_resolve_without_filters_passes_none_node_key(self, resolver, monkeypatch):
        """省略 filters（旧 4-参调用）时 node_key 为 None（legacy NULL 语义入口）。"""
        from unittest.mock import AsyncMock
        import app.services.custom_query.module_cell_resolver as mcr

        captured = {}

        async def _spy(db, project_id, year, section_id, cell_range, node_key=None):
            captured["node_key"] = node_key
            return []

        monkeypatch.setattr(mcr, "_query_note_cells", _spy)

        db = AsyncMock()
        await resolver.resolve(db, "note:五-1-1|A2:E2", "proj-1", 2025)

        assert captured["node_key"] is None

    @pytest.mark.asyncio
    async def test_resolve_filters_without_node_key_passes_none(self, resolver, monkeypatch):
        """filters 存在但无 node_key 键时 node_key 为 None。"""
        from unittest.mock import AsyncMock
        import app.services.custom_query.module_cell_resolver as mcr

        captured = {}

        async def _spy(db, project_id, year, section_id, cell_range, node_key=None):
            captured["node_key"] = node_key
            return []

        monkeypatch.setattr(mcr, "_query_note_cells", _spy)

        db = AsyncMock()
        await resolver.resolve(db, "note:五-1-1|A2:E2", "proj-1", 2025, {"other": "x"})

        assert captured["node_key"] is None

    @pytest.mark.asyncio
    async def test_dispatch_passes_filters_node_key_through(self, monkeypatch):
        """全链路：_dispatch(QueryRequest.filters) → resolve → _query_note_cells。

        用真实 QueryRequest 与真实 _dispatch，仅在最底层附注取数器打桩，
        证明 filters.node_key 不在中途被丢弃（F8：旧实现 _dispatch 丢 filters）。
        """
        from unittest.mock import AsyncMock
        import app.services.custom_query.module_cell_resolver as mcr
        from app.services.custom_query.business_fetchers import _dispatch
        from app.services.custom_query.query_orchestrator import QueryRequest

        captured = {}

        async def _spy(db, project_id, year, section_id, cell_range, node_key=None):
            captured["node_key"] = node_key
            captured["section_id"] = section_id
            return []

        monkeypatch.setattr(mcr, "_query_note_cells", _spy)

        req = QueryRequest(
            entry="business",
            project_id="proj-9",
            source="note:五-2-1|C3:D8",
            year=2024,
            filters={"node_key": "C777:parent"},
        )
        db = AsyncMock()
        result = await _dispatch(req, db, None)

        assert isinstance(result, dict)
        assert captured["node_key"] == "C777:parent"
        assert captured["section_id"] == "五-2-1"

    @pytest.mark.asyncio
    async def test_dispatch_report_module_ignores_node_key(self, monkeypatch):
        """report 模块不接收 node_key（node_key 仅对 note 有语义）。"""
        from unittest.mock import AsyncMock
        import app.services.custom_query.module_cell_resolver as mcr
        from app.services.custom_query.business_fetchers import _dispatch
        from app.services.custom_query.query_orchestrator import QueryRequest

        import inspect

        # _query_report_cells 签名保持 5 参，无 node_key —— 证明未误扩散
        sig = inspect.signature(mcr._query_report_cells)
        assert "node_key" not in sig.parameters

        async def _spy(db, project_id, year, report_type, cell_range):
            return []

        monkeypatch.setattr(mcr, "_query_report_cells", _spy)

        req = QueryRequest(
            entry="business",
            project_id="proj-9",
            source="report:balance_sheet|C2:C5",
            year=2024,
            filters={"node_key": "C777:consol"},
        )
        db = AsyncMock()
        result = await _dispatch(req, db, None)
        assert isinstance(result, dict)
        assert result["module"] == "report"


# ─── Task 3.2: _query_note_cells 节点过滤（真 ORM / 真 SQLite，P6）────────────
# spec: consol-node-key-isolation-and-shared-context（需求 3.1~3.2；设计 §五.1、P6、ADR-CNSC-004）
#
# 验证 custom query 附注取数的归属元组隔离：
#   - 有 node_key → 精确等值匹配该节点行；不读其它节点、不读 legacy、不读其它项目/年度/章节
#   - 无 node_key → 只读 legacy NULL 行，不回退任何节点行
#   - 稳定排序（ORDER BY id），不套根 legacy fallback
# 被测的是真实生产函数 _query_note_cells + ModuleCellResolver.resolve（禁用 mock 替换被测函数本身），
# 真 ConsolNoteData ORM 行落 SQLite，经 db.flush/commit 后真查询。

from datetime import datetime, timezone

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.models.consol_note_data_models import ConsolNoteData
from app.services.custom_query.module_cell_resolver import (
    _query_note_cells,
    module_cell_resolver,
)

# 复用 test_consol_push 的真集团夹具（真 SQLite 内存库 + 真 ORM 行）。
# 不可重命名 db/factory/group：db 夹具按参数名 `factory` 解析依赖，group 同理，
# pytest 以原始函数参数名解析 fixture 依赖，别名会导致 "fixture 'factory' not found"。
from tests.test_consol_push import (  # noqa: F401,E402
    Y,
    db,
    factory,
    group,
)

_SID = "note_5_1"


def _note_payload(tag: str) -> dict:
    """构造附注 data JSONB —— resolver 读 data['rows'] 的 code/name/year_end/... 列。

    用 ``name`` 列承载 tag，便于按 B2（name 列）断言命中了哪一行数据源。
    """
    return {"rows": [{"code": "1001", "name": tag, "year_end": 100, "year_begin": 90, "formula": None}]}


async def _add_note(db, *, project_id, year, section_id, node_key, data):
    rec = ConsolNoteData(
        project_id=project_id, year=year, section_id=section_id,
        node_key=node_key, data=data, is_stale=False,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(rec)
    await db.flush()
    return rec


def _b2_value(cells: list[dict]):
    """从 _query_note_cells 返回里取 B2（第 2 行 name 列）的 value。"""
    for c in cells:
        if c["cell_ref"] == "B2":
            return c["value"]
    return None


class TestQueryNoteCellsNodeFilter:
    """Task 3.2：_query_note_cells 按 project/year/section + 精确 node_key 过滤。

    **Validates: Requirements 3.1, 3.2**
    """

    @pytest.mark.asyncio
    async def test_node_key_exact_match_isolates_from_other_node(self, db, group):
        """P6：有 node_key → 只命中该节点行，不串到另一节点行。"""
        pid = group["G"].id
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key="G:parent", data=_note_payload("parent"))
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key="B:subsidiary", data=_note_payload("subB"))
        await db.commit()

        a = await _query_note_cells(db, str(pid), Y, _SID, "A2:E2", node_key="G:parent")
        b = await _query_note_cells(db, str(pid), Y, _SID, "A2:E2", node_key="B:subsidiary")
        assert _b2_value(a) == "parent"
        assert _b2_value(b) == "subB"

    @pytest.mark.asyncio
    async def test_node_key_does_not_read_legacy_null_row(self, db, group):
        """ADR-CNSC-004：有 node_key 但该节点无行时，不回退 legacy NULL 行（空结果）。"""
        pid = group["G"].id
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key=None, data=_note_payload("legacy"))
        await db.commit()

        # 即便是根 consol 键，custom query 也不套根 legacy fallback。
        cells = await _query_note_cells(db, str(pid), Y, _SID, "A2:E2", node_key="G:consol")
        assert _b2_value(cells) in (None, ""), "有键无行时不得回退 legacy"

    @pytest.mark.asyncio
    async def test_no_node_key_reads_only_legacy_null_row(self, db, group):
        """无 node_key → 只读 legacy NULL 行，不读任何节点行。"""
        pid = group["G"].id
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key=None, data=_note_payload("legacy"))
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key="G:consol", data=_note_payload("node"))
        await db.commit()

        cells = await _query_note_cells(db, str(pid), Y, _SID, "A2:E2", node_key=None)
        assert _b2_value(cells) == "legacy", "无键只命中 NULL 行，不读节点行"

    @pytest.mark.asyncio
    async def test_filters_project_year_section(self, db, group):
        """同 node_key 下跨项目 / 年度 / 章节的行互不命中。"""
        pid = group["G"].id
        other_pid = group["A"].id
        nk = "G:parent"
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key=nk, data=_note_payload("target"))
        await _add_note(db, project_id=other_pid, year=Y, section_id=_SID, node_key=nk, data=_note_payload("other_project"))
        await _add_note(db, project_id=pid, year=Y - 1, section_id=_SID, node_key=nk, data=_note_payload("other_year"))
        await _add_note(db, project_id=pid, year=Y, section_id="other_sec", node_key=nk, data=_note_payload("other_section"))
        await db.commit()

        cells = await _query_note_cells(db, str(pid), Y, _SID, "A2:E2", node_key=nk)
        assert _b2_value(cells) == "target", "只命中同项目+年度+章节+节点的行"

    @pytest.mark.asyncio
    async def test_resolve_end_to_end_passes_node_key_filter(self, db, group):
        """真编排器入口：ModuleCellResolver.resolve(filters={node_key}) 精确命中节点行。"""
        pid = group["G"].id
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key="G:parent", data=_note_payload("parent"))
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key="B:subsidiary", data=_note_payload("subB"))
        await db.commit()

        res = await module_cell_resolver.resolve(
            db, f"note:{_SID}|A2:E2", str(pid), Y, {"node_key": "B:subsidiary"},
        )
        assert res["module"] == "note"
        assert _b2_value(res["rows"]) == "subB"

    @pytest.mark.asyncio
    async def test_resolve_without_node_key_reads_legacy(self, db, group):
        """真编排器入口：无 node_key filters → 只读 legacy NULL 行。"""
        pid = group["G"].id
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key=None, data=_note_payload("legacy"))
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key="G:consol", data=_note_payload("node"))
        await db.commit()

        res = await module_cell_resolver.resolve(db, f"note:{_SID}|A2:E2", str(pid), Y)
        assert _b2_value(res["rows"]) == "legacy"

    @pytest.mark.asyncio
    async def test_stable_order_and_exact_match_sql_node_branch(self, db, group, monkeypatch):
        """稳定排序 + 精确等值变异证明（有键分支）。

        捕获发给 db.execute 的真实 ORM 语句并编译为 SQL 文本：
          - 必含 ``ORDER BY consol_note_data.id`` —— 若去掉排序，断言失败（非恒绿）；
          - 必含 ``consol_note_data.node_key = `` 的等值谓词；
          - 不得含 ``IS NULL``（有键时不走 legacy 分支）。
        """
        pid = group["G"].id
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key="G:parent", data=_note_payload("parent"))
        await db.commit()

        captured = []
        orig_execute = db.execute

        async def _spy_execute(stmt, *a, **kw):
            captured.append(stmt)
            return await orig_execute(stmt, *a, **kw)

        monkeypatch.setattr(db, "execute", _spy_execute)

        cells = await _query_note_cells(db, str(pid), Y, _SID, "A2:E2", node_key="G:parent")
        assert _b2_value(cells) == "parent"

        note_stmts = [s for s in captured if "consol_note_data" in str(s)]
        assert note_stmts, "应执行一次 consol_note_data 查询"
        sql = str(note_stmts[0])
        assert "ORDER BY consol_note_data.id" in sql, f"必须带稳定排序 ORDER BY id：{sql}"
        assert "consol_note_data.node_key = " in sql, f"有键时必须精确等值匹配 node_key：{sql}"
        assert "IS NULL" not in sql, f"有键时不得走 legacy NULL 分支：{sql}"

    @pytest.mark.asyncio
    async def test_sql_legacy_branch_uses_is_null(self, db, group, monkeypatch):
        """无键分支变异证明：SQL 走 ``node_key IS NULL``，不含等值谓词。"""
        pid = group["G"].id
        await _add_note(db, project_id=pid, year=Y, section_id=_SID, node_key=None, data=_note_payload("legacy"))
        await db.commit()

        captured = []
        orig_execute = db.execute

        async def _spy_execute(stmt, *a, **kw):
            captured.append(stmt)
            return await orig_execute(stmt, *a, **kw)

        monkeypatch.setattr(db, "execute", _spy_execute)

        cells = await _query_note_cells(db, str(pid), Y, _SID, "A2:E2", node_key=None)
        assert _b2_value(cells) == "legacy"

        note_stmts = [s for s in captured if "consol_note_data" in str(s)]
        assert note_stmts, "应执行一次 consol_note_data 查询"
        sql = str(note_stmts[0])
        assert "consol_note_data.node_key IS NULL" in sql, f"无键必须走 legacy NULL 分支：{sql}"
        assert "ORDER BY consol_note_data.id" in sql, f"必须带稳定排序 ORDER BY id：{sql}"
