# -*- coding: utf-8 -*-
"""D4-6 重要指标分析表契约 + 投影往返守卫（批次B 从零第一张）。

判据先行：
  1. build_contract_payload() 纳入 d46-managed 后，parse_contract 强校验通过，
     且该 sheet 含 1 张动态行 table（行身份=key），受管列 B/C/E/F/H，
     formula_mask 含 D/G 全 12 数据行。
  2. instrumentation_specs 计数与契约行 table 数对齐（_align_specs_to_sibling_tables 不抛）。
  3. build_store_projection_d46 → merge_projection_into_d46_rows 逐字段往返等值，
     formula 派生列不回写，行身份不串，元数据(name/formula/source)保留。
反向自检：去掉 D/G formula_mask 或改错行身份键必红。
"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.phase5_d4_indicator_sheet import (
    SHEET_KEY_D46,
    TABLE_KEY_D46,
    MANAGED_FIELD_SPECS_D46,
    formula_mask_cells_d46,
    build_store_projection_d46,
    merge_projection_into_d46_rows,
)

D46_SHEET_KEY = "d46-managed"


def _contract():
    return parse_contract(D4.build_contract_payload())


def test_d46_sheet_in_contract_and_parses():
    raw = D4.build_contract_payload()
    keys = [s["sheet_key"] for s in raw["sheets"]]
    assert D46_SHEET_KEY in keys, "d46-managed 未接入 build_contract_payload"
    parsed = _contract()  # 强校验不抛
    assert any(s.sheet_key == D46_SHEET_KEY for s in parsed.sheets)


def test_d46_single_dynamic_row_table_with_field_identity():
    parsed = _contract()
    sheet = next(s for s in parsed.sheets if s.sheet_key == D46_SHEET_KEY)
    row_tables = [t for t in sheet.tables if t.row_identity is not None]
    assert len(row_tables) == 1, "D4-6 应恰好 1 张动态行 table"
    t = row_tables[0]
    assert t.table_key == TABLE_KEY_D46
    # 行身份是字段 key（非 UUID 硬编码）
    assert "key" in str(t.row_identity.json_pointer)


def test_d46_formula_mask_covers_diff_columns():
    parsed = _contract()
    sheet = next(s for s in parsed.sheets if s.sheet_key == D46_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    mask = set(t.formula_mask)
    # D/G 列 13-24 全在 mask
    for row in range(13, 25):
        assert f"D{row}" in mask, f"D{row} 差异1 公式列未进 formula_mask"
        assert f"G{row}" in mask, f"G{row} 差异2 公式列未进 formula_mask"
    assert set(formula_mask_cells_d46()) == mask


def test_d46_managed_columns_are_bcefh():
    parsed = _contract()
    sheet = next(s for s in parsed.sheets if s.sheet_key == D46_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    cols = {f.cell.column for f in t.fields}
    assert cols == {"B", "C", "E", "F", "H"}, f"受管列应为 B/C/E/F/H，实际 {cols}"


def _sample_store() -> str:
    return json.dumps(
        [
            {"key": "ar-to-assets", "name": "应收账款/总资产", "formula": "f1", "source": "s1",
             "current": 0.3, "prior": 0.25, "analysis1": "升", "industryAvg": 0.28, "analysis2": "合理"},
            {"key": "net-profit-margin", "name": "销售净利率", "formula": "f2", "source": "s2",
             "current": 0.1, "prior": 0.12, "analysis1": "降", "industryAvg": 0.11, "analysis2": "关注"},
        ],
        ensure_ascii=False,
    )


def test_d46_projection_merge_roundtrip_equal():
    parsed = _contract()
    store = _sample_store()
    proj = build_store_projection_d46(store, contract=parsed)
    merged = merge_projection_into_d46_rows(projection=proj, base_payload=store)
    orig = json.loads(store)
    assert len(merged) == 2
    for i in range(2):
        assert merged[i]["key"] == orig[i]["key"]  # 身份不串
        assert merged[i]["current"] == orig[i]["current"]
        assert merged[i]["prior"] == orig[i]["prior"]
        assert merged[i]["analysis1"] == orig[i]["analysis1"]
        assert merged[i]["industryAvg"] == orig[i]["industryAvg"]
        assert merged[i]["analysis2"] == orig[i]["analysis2"]
        # 元数据保留（不受管、不丢）
        assert merged[i]["name"] == orig[i]["name"]
        assert merged[i]["formula"] == orig[i]["formula"]


def test_d46_projection_rejects_missing_identity():
    parsed = _contract()
    bad = json.dumps([{"current": 1}], ensure_ascii=False)  # 缺 key
    with pytest.raises(ValueError):
        build_store_projection_d46(bad, contract=parsed)


def test_d46_projection_rejects_duplicate_identity():
    parsed = _contract()
    bad = json.dumps([{"key": "x", "current": 1}, {"key": "x", "current": 2}], ensure_ascii=False)
    with pytest.raises(ValueError):
        build_store_projection_d46(bad, contract=parsed)
