"""K1-6 会计政策检查 — 导入导出行映射单元测试."""

from __future__ import annotations

from app.routers.wp_render_strategies._k1_import_export import (
    _K1_6_COMBO_HEADERS,
    _K1_6_PEER_HEADERS,
    _K1_6_K2_HEADERS,
    _k1_6_parse_combos,
    _k1_6_parse_peers,
    _k1_6_parse_k2,
    _k1_6_parse_texts,
    _k1_6_combo_export_rows,
    _k1_6_peer_export_rows,
    _k1_6_k2_export_rows,
)


def test_k1_6_headers_present():
    assert len(_K1_6_COMBO_HEADERS) == 4
    assert len(_K1_6_PEER_HEADERS) == 3
    assert len(_K1_6_K2_HEADERS) == 4


def test_k1_6_combo_parse_export_roundtrip():
    headers = _K1_6_COMBO_HEADERS
    row = (1, "押金和保证金", "账龄分析法", "备注")
    parsed = _k1_6_parse_combos([row], headers)
    assert len(parsed) == 1
    assert parsed[0]["basis"] == "押金和保证金"
    exported = _k1_6_combo_export_rows(parsed)
    assert exported[0][1] == "押金和保证金"


def test_k1_6_peer_parse():
    headers = _K1_6_PEER_HEADERS
    row = ("海螺水泥", "组合测试政策", "部分一致")
    parsed = _k1_6_parse_peers([row], headers)
    assert parsed[0]["company"] == "海螺水泥"
    assert parsed[0]["comparable"] == "部分一致"
    exported = _k1_6_peer_export_rows(parsed)
    assert exported[0][0] == "海螺水泥"


def test_k1_6_k2_rates_parse():
    headers = _K1_6_K2_HEADERS
    row = ("1年以内", 0.01, 0.02, "前瞻调整")
    parsed = _k1_6_parse_k2([row], headers)
    assert parsed[0]["agingBucket"] == "1年以内"
    assert parsed[0]["adjustedRate"] == 0.02
    exported = _k1_6_k2_export_rows(parsed)
    assert exported[0][2] == 0.02


def test_k1_6_text_fields_parse():
    headers = ["字段", "内容"]
    rows = [("审计程序", "程序1"), ("审计结论", "结论A")]
    texts = _k1_6_parse_texts(rows, headers)
    assert texts["审计程序"] == "程序1"
    assert texts["审计结论"] == "结论A"
