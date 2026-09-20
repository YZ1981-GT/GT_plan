# -*- coding: utf-8 -*-
"""D4-18 营业收入截止测试（单据到账）契约 + 投影往返守卫（批次B 第三张）。

与 D4-17 同构，列序反转（发货单 A-E / 记账凭证 F-J）。
"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.phase5_d4_cutoff_backward_sheet import (
    TABLE_KEY_D418,
    formula_mask_cells_d418,
    build_store_projection_d418,
    merge_projection_into_d418_rows,
)

D418_SHEET_KEY = "d418-managed"


@pytest.fixture(autouse=True)
def _enable_d418(monkeypatch):
    monkeypatch.setattr(D4, "_INCLUDE_D418_CUTOFF_SHEET", True, raising=False)


def _contract():
    return parse_contract(D4.build_contract_payload())


def test_d418_sheet_in_contract_and_parses():
    keys = [s["sheet_key"] for s in D4.build_contract_payload()["sheets"]]
    assert D418_SHEET_KEY in keys
    assert any(s.sheet_key == D418_SHEET_KEY for s in _contract().sheets)


def test_d418_single_dynamic_row_table_identity_id():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D418_SHEET_KEY)
    row_tables = [t for t in sheet.tables if t.row_identity is not None]
    assert len(row_tables) == 1
    assert row_tables[0].table_key == TABLE_KEY_D418
    assert "id" in str(row_tables[0].row_identity.json_pointer)


def test_d418_managed_columns_a_to_j():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D418_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    assert {f.cell.column for f in t.fields} == set("ABCDEFGHIJ")


def test_d418_formula_mask_covers_k_column():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D418_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    mask = set(t.formula_mask)
    for row in range(13, 24):
        assert f"K{row}" in mask
    assert set(formula_mask_cells_d418()) == mask


def test_d418_projection_merge_roundtrip_equal():
    parsed = _contract()
    store = json.dumps(
        [
            {"id": "r1", "deliveryDate": "2025-12-28", "deliveryNo": "D1", "deliveryProduct": "P",
             "deliveryQty": "3", "deliveryAmount": 300, "voucherDate": "2026-01-03", "voucherNo": "V1",
             "voucherProduct": "P", "voucherQty": "3", "voucherAmount": 300, "isCutoff": False, "remark": "跨期"},
        ],
        ensure_ascii=False,
    )
    proj = build_store_projection_d418(store, contract=parsed)
    merged = merge_projection_into_d418_rows(projection=proj, base_payload=store)
    o = json.loads(store)
    assert merged[0]["id"] == o[0]["id"]
    assert merged[0]["deliveryDate"] == o[0]["deliveryDate"]
    assert merged[0]["voucherAmount"] == o[0]["voucherAmount"]
    assert merged[0]["remark"] == o[0]["remark"]
    assert merged[0]["isCutoff"] == o[0]["isCutoff"]


def test_d418_rejects_missing_and_duplicate_identity():
    parsed = _contract()
    with pytest.raises(ValueError):
        build_store_projection_d418(json.dumps([{"deliveryNo": "x"}]), contract=parsed)
    with pytest.raises(ValueError):
        build_store_projection_d418(json.dumps([{"id": "a"}, {"id": "a"}]), contract=parsed)
