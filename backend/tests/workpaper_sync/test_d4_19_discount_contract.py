# -*- coding: utf-8 -*-
"""D4-19 销售折扣与折让检查契约 + 投影往返守卫（批次B 第四张）。"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.phase5_d4_discount_sheet import (
    TABLE_KEY_D419,
    formula_mask_cells_d419,
    build_store_projection_d419,
    merge_projection_into_d419_rows,
)

D419_SHEET_KEY = "d419-managed"


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setattr(D4, "_INCLUDE_D419_DISCOUNT_SHEET", True, raising=False)


def _contract():
    return parse_contract(D4.build_contract_payload())


def test_d419_in_contract_and_parses():
    assert D419_SHEET_KEY in [s["sheet_key"] for s in D4.build_contract_payload()["sheets"]]
    assert any(s.sheet_key == D419_SHEET_KEY for s in _contract().sheets)


def test_d419_single_dynamic_row_identity_id():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D419_SHEET_KEY)
    rt = [t for t in sheet.tables if t.row_identity is not None]
    assert len(rt) == 1 and rt[0].table_key == TABLE_KEY_D419
    assert "id" in str(rt[0].row_identity.json_pointer)


def test_d419_managed_columns_exclude_ratio_E():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D419_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    cols = {f.cell.column for f in t.fields}
    assert cols == set("ABCD") | set("FGHIJKLMN")
    assert "E" not in cols  # 折扣比例是派生列


def test_d419_formula_mask_covers_E():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D419_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    mask = set(t.formula_mask)
    for row in range(13, 24):
        assert f"E{row}" in mask
    assert set(formula_mask_cells_d419()) == mask


def test_d419_roundtrip_equal():
    parsed = _contract()
    store = json.dumps(
        [{"id": "r1", "customerName": "甲", "discountType": "现金折扣", "revenueAmount": 1000,
          "discountAmount": 50, "discountRate": 0.05, "reason": "早付", "voucherDate": "2025-06-01",
          "voucherNo": "V1", "accountSubject": "6001", "detailSubject": "折扣", "debitAmount": 50,
          "creditAmount": 0, "approvalDate": "2025-05-30", "approver": "李", "remark": "x"}],
        ensure_ascii=False,
    )
    proj = build_store_projection_d419(store, contract=parsed)
    merged = merge_projection_into_d419_rows(projection=proj, base_payload=store)
    o = json.loads(store)
    assert merged[0]["customerName"] == o[0]["customerName"]
    assert merged[0]["discountAmount"] == o[0]["discountAmount"]
    assert merged[0]["approver"] == o[0]["approver"]
    assert merged[0]["remark"] == o[0]["remark"]
    assert merged[0]["discountRate"] == o[0]["discountRate"]  # 派生列不被 merge 动


def test_d419_rejects_missing_and_duplicate_identity():
    parsed = _contract()
    with pytest.raises(ValueError):
        build_store_projection_d419(json.dumps([{"customerName": "x"}]), contract=parsed)
    with pytest.raises(ValueError):
        build_store_projection_d419(json.dumps([{"id": "a"}, {"id": "a"}]), contract=parsed)
