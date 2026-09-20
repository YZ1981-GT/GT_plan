# -*- coding: utf-8 -*-
"""D4-10 重要客户销售价格分析契约 + 投影往返守卫（批次B 第六张）。dict store（{rows,...}）。"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.phase5_d4_customer_price_sheet import (
    TABLE_KEY_D410,
    formula_mask_cells_d410,
    build_store_projection_d410,
    merge_projection_into_d410_rows,
)

D410_SHEET_KEY = "d410-managed"


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setattr(D4, "_INCLUDE_D410_PRICE_SHEET", True, raising=False)


def _contract():
    return parse_contract(D4.build_contract_payload())


def test_d410_in_contract_and_parses():
    assert D410_SHEET_KEY in [s["sheet_key"] for s in D4.build_contract_payload()["sheets"]]
    assert any(s.sheet_key == D410_SHEET_KEY for s in _contract().sheets)


def test_d410_single_dynamic_row_identity_rowid():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D410_SHEET_KEY)
    rt = [t for t in sheet.tables if t.row_identity is not None]
    assert len(rt) == 1 and rt[0].table_key == TABLE_KEY_D410
    assert "rowId" in str(rt[0].row_identity.json_pointer)


def test_d410_managed_columns_exclude_ordinal_ratio_diff():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D410_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    cols = {f.cell.column for f in t.fields}
    assert cols == {"B", "C", "D", "F", "H", "I", "K", "L", "N"}
    for excluded in ("A", "E", "G", "J", "M"):
        assert excluded not in cols


def test_d410_formula_mask_covers_ratio_and_diff():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D410_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    mask = set(t.formula_mask)
    for row in range(13, 34):
        for col in ("E", "G", "J", "M"):
            assert f"{col}{row}" in mask
    assert set(formula_mask_cells_d410()) == mask


def test_d410_dict_roundtrip_preserves_totals():
    parsed = _contract()
    store = json.dumps(
        {"rows": [{"rowId": "c1", "seq": 1, "customer": "大客户", "product": "A", "amount": 1000,
                   "quantity": 100, "unitPrice": 10, "avgPrice": 9, "avgReason": "",
                   "marketPrice": 11, "marketReason": "高"}],
         "totalAmount": 5000, "totalQuantity": 500},
        ensure_ascii=False,
    )
    proj = build_store_projection_d410(store, contract=parsed)
    merged = merge_projection_into_d410_rows(projection=proj, base_payload=store)
    assert merged["rows"][0]["customer"] == "大客户"
    assert merged["rows"][0]["amount"] == 1000
    assert merged["rows"][0]["marketReason"] == "高"
    # 表级标量保留（不被 merge 丢）
    assert merged["totalAmount"] == 5000
    assert merged["totalQuantity"] == 500


def test_d410_legacy_bare_list_tolerated_empty():
    """legacy bare list（无 {rows} dict）视为空投影，不 fail-closed 打挂全 entry。"""
    parsed = _contract()
    proj = build_store_projection_d410(json.dumps([{"k": 1}]), contract=parsed)
    assert proj.row_keys.get(TABLE_KEY_D410, ()) == ()


def test_d410_dict_missing_rowid_fails_closed():
    parsed = _contract()
    with pytest.raises(ValueError):
        build_store_projection_d410(json.dumps({"rows": [{"customer": "x"}]}), contract=parsed)
