"""K1-11 关联方及交易检查表 — 导入导出行映射单元测试."""

from __future__ import annotations

from app.routers.wp_render_strategies._k1_import_export import (
    _K1_11_HEADERS,
    _k1_11_export_row,
    _k1_11_parse_row,
)


def test_k1_11_headers_count():
    assert len(_K1_11_HEADERS) == 16


def test_k1_11_export_row_auto_calc():
    row = _k1_11_export_row({
        "name": "甲公司",
        "relation": "联营企业",
        "beginBalance": 100,
        "debit": 50,
        "credit": 20,
        "provision": 10,
        "aging": "2年",
        "nature": "往来款",
        "postCollection": 5,
        "isFair": "是",
        "isDisclosed": "是",
        "capitalOccupation": "否",
        "indexNo": "K1-12",
        "remark": "测试",
    })
    assert row[0] == "甲公司"
    assert row[5] == 130  # 期末
    assert row[7] == 120  # 账面价值


def test_k1_11_parse_export_roundtrip():
    headers = _K1_11_HEADERS
    src = (
        "乙公司", "控股股东", 200, 0, 50, 150, 20, 130,
        "1-2年", "保证金", 10, "待评估", "是", "否", "K1-12", "备注",
    )
    parsed = _k1_11_parse_row(src, headers)
    exported = _k1_11_export_row(parsed)
    assert exported[0] == "乙公司"
    assert exported[5] == 150
    assert exported[7] == 130
