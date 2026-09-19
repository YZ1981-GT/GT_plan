"""K1-1 审定表 — 导入导出行映射单元测试."""

from __future__ import annotations

from app.routers.wp_render_strategies._k1_import_export import (
    _K1_1_WIDE_HEADERS,
    _K1_1_PORTFOLIO_DEFS,
    _k1_1_parse_wide_rows,
    _k1_1_row_values,
    _k1_1_audited,
)


def test_k1_1_wide_headers_count():
    assert len(_K1_1_WIDE_HEADERS) == 12


def test_k1_1_audited_formula():
    assert _k1_1_audited(1000, 50, -10) == 1040


def test_k1_1_row_values_from_responses():
    responses = {
        "K1-1-receivable-r0-prior-unadj": "100",
        "K1-1-receivable-r0-prior-aje": "0",
        "K1-1-receivable-r0-prior-rje": "0",
        "K1-1-receivable-r0-unadj": "1000",
        "K1-1-receivable-r0-aje": "20",
        "K1-1-receivable-r0-rje": "0",
        "K1-1-receivable-r0-remark": "测试原因",
    }
    row = _k1_1_row_values(responses, "receivable", "r0", "单项计提")
    assert row[0] == "单项计提"
    assert row[1] == 100  # prior unadj
    assert row[8] == 1020  # audited
    assert row[9] == 920  # change amount
    assert row[11] == "测试原因"


def test_k1_1_parse_wide_rows_by_label():
    headers = _K1_1_WIDE_HEADERS
    src = (
        "账龄组合", 500, 0, 0, 500,
        800, 10, 0, 810,
        310, 0.62, "余额增加",
    )
    parsed = _k1_1_parse_wide_rows([src], headers, _K1_1_PORTFOLIO_DEFS)
    assert len(parsed) == 1
    assert parsed[0]["rowKey"] == "r1"
    assert parsed[0]["label"] == "账龄组合"
    assert parsed[0]["unadj"] == 800
    assert parsed[0]["aje"] == 10
    assert parsed[0]["remark"] == "余额增加"
