# -*- coding: utf-8 -*-
"""D4-11 产品销售价格分析契约 + 投影往返守卫（批次B 第五张）。"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.phase5_d4_product_price_sheet import (
    TABLE_KEY_D411,
    formula_mask_cells_d411,
    build_store_projection_d411,
    merge_projection_into_d411_rows,
)

D411_SHEET_KEY = "d411-managed"


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setattr(D4, "_INCLUDE_D411_PRICE_SHEET", True, raising=False)


def _contract():
    return parse_contract(D4.build_contract_payload())


def test_d411_in_contract_and_parses():
    assert D411_SHEET_KEY in [s["sheet_key"] for s in D4.build_contract_payload()["sheets"]]
    assert any(s.sheet_key == D411_SHEET_KEY for s in _contract().sheets)


def test_d411_single_dynamic_row_identity_rowid():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D411_SHEET_KEY)
    rt = [t for t in sheet.tables if t.row_identity is not None]
    assert len(rt) == 1 and rt[0].table_key == TABLE_KEY_D411
    assert "rowId" in str(rt[0].row_identity.json_pointer)


def test_d411_managed_columns_exclude_ordinal_and_diff():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D411_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    cols = {f.cell.column for f in t.fields}
    # A 序号非受管 / J,L 差异率派生非受管
    assert cols == {"B", "C", "D", "E", "F", "G", "H", "I", "K", "M", "N", "O"}
    assert "A" not in cols and "J" not in cols and "L" not in cols


def test_d411_formula_mask_covers_J_L():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D411_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    mask = set(t.formula_mask)
    for row in range(12, 22):
        assert f"J{row}" in mask and f"L{row}" in mask
    assert set(formula_mask_cells_d411()) == mask


def test_d411_roundtrip_equal():
    parsed = _contract()
    store = json.dumps(
        [{"rowId": "p1", "customer": "甲", "product": "A", "unitPrice": 10, "quantity": 5,
          "invoiceDate": "2025-03-01", "orderNo": "O1", "orderDate": "2025-02-20", "listPrice": 9,
          "marketPrice": 11, "reason": "", "priceSource": "idx", "remark": "r"}],
        ensure_ascii=False,
    )
    proj = build_store_projection_d411(store, contract=parsed)
    merged = merge_projection_into_d411_rows(projection=proj, base_payload=store)
    o = json.loads(store)
    assert merged[0]["rowId"] == o[0]["rowId"]
    assert merged[0]["unitPrice"] == o[0]["unitPrice"]
    assert merged[0]["listPrice"] == o[0]["listPrice"]
    assert merged[0]["priceSource"] == o[0]["priceSource"]
    assert merged[0]["remark"] == o[0]["remark"]


def test_d411_rejects_missing_and_duplicate_identity():
    parsed = _contract()
    with pytest.raises(ValueError):
        build_store_projection_d411(json.dumps([{"customer": "x"}]), contract=parsed)
    with pytest.raises(ValueError):
        build_store_projection_d411(json.dumps([{"rowId": "a"}, {"rowId": "a"}]), contract=parsed)
