"""Tests for module_cell_resolver 的源 URI 解析 / 序列化（Req 13.1）

Property 24: source URI 解析 round-trip

跨模块单元格级取数（``ModuleCellResolver`` / ``_query_*_cells`` / 虚拟 sheet 提取）已随
advanced-query-linkage-closure 任务 34 删除（ADR-AQL-13，AQ-25），其路由、输出形态与 node_key 用例一并删除；
这类源键在业务视图按未知数据源 400，见 ``tests/advanced_query_linkage/test_aql_source_registry.py``。
"""

from hypothesis import given, settings, strategies as st

from app.services.custom_query.module_cell_resolver import (
    parse_source_uri,
    format_source_uri,
)


# ─── Strategies ──────────────────────────────────────────────────────────────

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
_SINGLE_COL = st.sampled_from(list("ABCDEFG"))
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
