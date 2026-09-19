# -*- coding: utf-8 -*-
"""D4-17 营业收入截止测试（账到单据）契约 + 投影往返守卫（批次B 第二张）。

判据先行：
  1. build_contract_payload() 纳入 d417-managed 后 parse_contract 强校验通过，
     该 sheet 含 1 张动态行 table（行身份=id），受管列 A-J（10 列），formula_mask 含 K 全数据行。
  2. build_store_projection_d417 → merge_projection_into_d417_rows 逐字段往返等值，
     K(是否跨期) 派生不回写，remark 元数据保留，行身份不串，缺/重复身份拒绝。
"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.phase5_d4_cutoff_forward_sheet import (
    TABLE_KEY_D417,
    formula_mask_cells_d417,
    build_store_projection_d417,
    merge_projection_into_d417_rows,
)

D417_SHEET_KEY = "d417-managed"


@pytest.fixture(autouse=True)
def _enable_d417(monkeypatch):
    """D4-17 provider 已完成并单测验证，但生产开关 `_INCLUDE_D417_CUTOFF_SHEET` 暂关
    （共享 entry 的 D4-9 阻塞 live rematerialize，见 provider 注释）。本守卫验证「开启后
    契约/投影正确」，故在测试内翻开开关，与生产 live 发布解耦。"""
    monkeypatch.setattr(D4, "_INCLUDE_D417_CUTOFF_SHEET", True, raising=False)


def _contract():
    return parse_contract(D4.build_contract_payload())


def test_d417_sheet_in_contract_and_parses():
    raw = D4.build_contract_payload()
    keys = [s["sheet_key"] for s in raw["sheets"]]
    assert D417_SHEET_KEY in keys, "d417-managed 未接入 build_contract_payload"
    parsed = _contract()
    assert any(s.sheet_key == D417_SHEET_KEY for s in parsed.sheets)


def test_d417_single_dynamic_row_table_identity_id():
    parsed = _contract()
    sheet = next(s for s in parsed.sheets if s.sheet_key == D417_SHEET_KEY)
    row_tables = [t for t in sheet.tables if t.row_identity is not None]
    assert len(row_tables) == 1
    t = row_tables[0]
    assert t.table_key == TABLE_KEY_D417
    assert "id" in str(t.row_identity.json_pointer)


def test_d417_managed_columns_a_to_j():
    parsed = _contract()
    sheet = next(s for s in parsed.sheets if s.sheet_key == D417_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    cols = {f.cell.column for f in t.fields}
    assert cols == set("ABCDEFGHIJ"), f"受管列应为 A-J，实际 {cols}"


def test_d417_formula_mask_covers_k_column():
    parsed = _contract()
    sheet = next(s for s in parsed.sheets if s.sheet_key == D417_SHEET_KEY)
    t = next(tt for tt in sheet.tables if tt.row_identity is not None)
    mask = set(t.formula_mask)
    for row in range(13, 24):
        assert f"K{row}" in mask, f"K{row} 是否跨期派生列未进 formula_mask"
    assert set(formula_mask_cells_d417()) == mask


def _sample() -> str:
    return json.dumps(
        [
            {"id": "r1", "voucherDate": "2025-12-20", "voucherNo": "V1", "voucherProduct": "P",
             "voucherQty": "10", "voucherAmount": 1000, "deliveryDate": "2026-01-05", "deliveryNo": "D1",
             "deliveryProduct": "P", "deliveryQty": "10", "deliveryAmount": 1000, "isCutoff": False, "remark": "跨期"},
            {"id": "r2", "voucherDate": "2025-12-10", "voucherNo": "V2", "voucherProduct": "Q",
             "voucherQty": "5", "voucherAmount": 500, "deliveryDate": "2025-12-15", "deliveryNo": "D2",
             "deliveryProduct": "Q", "deliveryQty": "5", "deliveryAmount": 500, "isCutoff": True, "remark": ""},
        ],
        ensure_ascii=False,
    )


def test_d417_projection_merge_roundtrip_equal():
    parsed = _contract()
    store = _sample()
    proj = build_store_projection_d417(store, contract=parsed)
    merged = merge_projection_into_d417_rows(projection=proj, base_payload=store)
    orig = json.loads(store)
    assert len(merged) == 2
    for i in range(2):
        assert merged[i]["id"] == orig[i]["id"]
        assert merged[i]["voucherAmount"] == orig[i]["voucherAmount"]
        assert merged[i]["deliveryDate"] == orig[i]["deliveryDate"]
        assert merged[i]["voucherProduct"] == orig[i]["voucherProduct"]
        # remark 元数据保留（不受管、不丢）
        assert merged[i]["remark"] == orig[i]["remark"]
        # isCutoff(K 派生)在 store 里仍是原值（merge 不动它，因不在受管字段）
        assert merged[i]["isCutoff"] == orig[i]["isCutoff"]


def test_d417_rejects_missing_and_duplicate_identity():
    parsed = _contract()
    with pytest.raises(ValueError):
        build_store_projection_d417(json.dumps([{"voucherNo": "x"}]), contract=parsed)
    with pytest.raises(ValueError):
        build_store_projection_d417(
            json.dumps([{"id": "a"}, {"id": "a"}]), contract=parsed
        )
