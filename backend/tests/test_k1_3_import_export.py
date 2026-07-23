"""K1-3 坏账准备明细 — 导入导出行映射单元测试."""

from __future__ import annotations

from app.routers.wp_render_strategies._k1_import_export import (
    _K1_3_MAIN_HEADERS,
    _K1_3_STAGE_HEADERS,
    _K1_3_TEXT_MAP,
    _k1_3_main_export_rows,
    _k1_3_parse_main,
    _k1_3_parse_stage,
)


def test_k1_3_headers_present():
    assert len(_K1_3_MAIN_HEADERS) == 14
    assert len(_K1_3_STAGE_HEADERS) == 4


def test_k1_3_main_parse_export_roundtrip():
    headers = _K1_3_MAIN_HEADERS
    row = (
        '账龄组合', 'combo',
        100, 0, 100,
        50, 0, 10, 5, 0,
        135, 0, 135, '计提增加',
    )
    parsed = _k1_3_parse_main([row], headers)
    assert len(parsed) == 1
    assert parsed[0]['label'] == '账龄组合'
    assert parsed[0]['currentProvision'] == 50
    assert parsed[0]['reason'] == '计提增加'
    exported = _k1_3_main_export_rows({'mainRows': parsed})
    assert exported[0][0] == '账龄组合'
    assert exported[0][5] == 50


def test_k1_3_stage_parse():
    headers = _K1_3_STAGE_HEADERS
    row = ('第一阶段转入第二阶段', 1000, 200, 50)
    parsed = _k1_3_parse_stage([row], headers)
    assert parsed[0]['stage1'] == 1000
    assert parsed[0]['stage2'] == 200
    assert parsed[0]['editable'] is True


def test_k1_3_text_map_keys():
    assert '审计说明' in _K1_3_TEXT_MAP
    assert _K1_3_TEXT_MAP['审计说明'] == 'auditNote'
