# -*- coding: utf-8 -*-
"""D4-36 其他业务收入截止性测试守卫（同 sheet 双动态区 · dict store，2026-09-20 落地 gen70）。

引擎支持（有真实动态行维度）：2 dynamic 区（账到单据 forward / 单据到账 backward），单 dict store
D4-36-data（{forward,backward,...params}），已过 rematerialize（gen70，无 FooterAnchorDrift/RoundtripEquivalenceError）。

守卫：①契约 parse + 双区几何（footer marker=截止日期全文，同 marker 靠 first_row 消歧）；
②alignment bijection；③双区 projection/merge 往返（id 保留、两区不串、参数标量保留）；
④dict-block 3-tuple 门面；⑤live 契约含 D4-36。
"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
import app.services.workpaper_sync.phase5_d4_other_cutoff_sheet as C
from app.services.workpaper_sync.contracts import parse_contract


def _contract():
    return parse_contract(D4.build_contract_payload())


def test_sheet_payload_dual_region_shape():
    sp = C.sheet_payload_d436()
    assert sp["sheet_key"] == "d436-managed"
    assert len(sp["tables"]) == 2
    fwd = next(t for t in sp["tables"] if t["table_key"] == "d4_36_forward")
    bwd = next(t for t in sp["tables"] if t["table_key"] == "d4_36_backward")
    for t in (fwd, bwd):
        assert t["row_identity"] is not None
        assert t["delete_policy"] == "tombstone"
        assert t["formula_mask"] == []  # K 跨期为手工标记，非 Excel 公式
    assert fwd["uuid_col"] == "L"
    assert bwd["uuid_col"] == "M"
    assert fwd["uuid_col"] != bwd["uuid_col"]
    # footer marker 用整格全文（精确等值匹配），两区同文本靠 first_row 消歧
    assert fwd["footer_anchor"]["marker"] == "截止日期：202X年12月31日"
    assert bwd["footer_anchor"]["marker"] == "截止日期：202X年12月31日"
    # 11 字段（voucher* A-E / doc* F-J / isCrossing K）
    assert len(fwd["fields"]) == 11
    assert len(bwd["fields"]) == 11


def test_alignment_bijection_holds():
    from app.services.workpaper_sync.projection_first_publication import _align_specs_to_sibling_tables
    from app.services.workpaper_sync.phase5_d4_29_customer_detail import row_oriented_sheets

    contract = _contract()
    specs = tuple(D4.instrumentation_specs())
    sheets = row_oriented_sheets(contract)
    total = sum(len([t for t in s.tables if t.row_identity is not None]) for s in sheets)
    assert len(specs) == total
    primary = next(t for s in sheets for t in s.tables if t.row_identity is not None)
    _align_specs_to_sibling_tables(provider=D4, contract=contract, primary=primary)


def test_projection_merge_roundtrip_dual_region():
    contract = _contract()
    store = {
        "forward": [
            {"id": "ct-f1", "voucherDate": "2024-12-30", "voucherNo": "V1", "voucherProduct": "甲",
             "voucherQty": "10", "voucherAmount": 1000, "docDate": "2025-01-03", "docNo": "D1",
             "docProduct": "甲", "docQty": "10", "docAmount": 1000, "isCrossing": "×"},
        ],
        "backward": [
            {"id": "ct-b1", "voucherDate": "2025-01-05", "voucherNo": "V2", "voucherProduct": "乙",
             "voucherQty": "5", "voucherAmount": 500, "docDate": "2024-12-28", "docNo": "D2",
             "docProduct": "乙", "docQty": "5", "docAmount": 500, "isCrossing": "×"},
            {"id": "ct-b2", "voucherDate": "2024-12-20", "voucherNo": "V3", "voucherProduct": "丙",
             "voucherQty": "3", "voucherAmount": 300, "docDate": "2024-12-19", "docNo": "D3",
             "docProduct": "丙", "docQty": "3", "docAmount": 300, "isCrossing": "√"},
        ],
        "cutoffDate": "2024-12-31", "daysBefore": 5, "daysAfter": 5, "amountThreshold": 100,
    }
    proj = C.build_store_projection_d436(json.dumps(store, ensure_ascii=False), contract=contract)
    # fwd 1*11 + bwd 2*11 = 33
    assert len(proj.values) == 33
    assert proj.row_keys["d4_36_forward"] == ("ct-f1",)
    assert proj.row_keys["d4_36_backward"] == ("ct-b1", "ct-b2")
    assert proj.get("d4_36_forward/ct-f1/voucher_amount").value == 1000
    assert proj.get("d4_36_backward/ct-b1/is_crossing").value == "×"

    base = {"forward": [dict(r) for r in store["forward"]], "backward": [dict(r) for r in store["backward"]],
            "cutoffDate": "2024-12-31", "daysBefore": 5, "daysAfter": 5, "amountThreshold": 100}
    for r in base["forward"]:
        r["voucherAmount"] = 0; r["isCrossing"] = ""
    for r in base["backward"]:
        r["docAmount"] = 0
    merged, applied, visited = C.merge_d436_from_projection(
        projection=proj, base_state=json.dumps(base, ensure_ascii=False)
    )
    assert merged["forward"][0]["voucherAmount"] == 1000
    assert merged["forward"][0]["isCrossing"] == "×"
    assert merged["backward"][0]["docAmount"] == 500
    assert merged["backward"][1]["docAmount"] == 300
    # id 保留，两区不串
    assert merged["forward"][0]["id"] == "ct-f1"
    assert merged["backward"][1]["id"] == "ct-b2"
    # 参数标量保留（不受管）
    assert merged["cutoffDate"] == "2024-12-31"
    assert merged["daysBefore"] == 5
    assert merged["amountThreshold"] == 100


def test_merge_3tuple_signature():
    contract = _contract()
    proj = C.build_store_projection_d436("{}", contract=contract)
    result = C.merge_d436_from_projection(projection=proj, base_state=None)
    assert isinstance(result, tuple) and len(result) == 3
    merged, applied, visited = result
    assert isinstance(merged, dict) and isinstance(applied, int) and isinstance(visited, int)


def test_live_contract_contains_d436():
    assert D4._INCLUDE_D436_CUTOFF_SHEET is True
    contract = _contract()
    sheet_keys = {s.sheet_key for s in contract.sheets}
    assert "d436-managed" in sheet_keys
    assert hasattr(D4, "STORE_ITEM_ID_D436_DICT")
    assert C.STORE_ITEM_ID_D436 == "D4-36-data"
    assert C.STORE_ITEM_ID_D436 in D4.STORE_ITEM_IDS


def test_missing_or_duplicate_id_raises():
    contract = _contract()
    with pytest.raises(ValueError):
        C.build_store_projection_d436(json.dumps({"forward": [{"voucherNo": "无id"}], "backward": []}), contract=contract)
    with pytest.raises(ValueError):
        C.build_store_projection_d436(
            json.dumps({"forward": [{"id": "x"}, {"id": "x"}], "backward": []}), contract=contract
        )
    proj = C.build_store_projection_d436(json.dumps({"forward": "bad", "backward": {}}), contract=contract)
    assert len(proj.values) == 0
