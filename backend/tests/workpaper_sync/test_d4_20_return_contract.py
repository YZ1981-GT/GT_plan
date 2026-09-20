# -*- coding: utf-8 -*-
"""D4-20 销售退货检查表契约 + 投影往返守卫（批次B 第七张，4 region）。"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
from app.services.workpaper_sync.contracts import parse_contract
import app.services.workpaper_sync.phase5_d4_return_sheet as R

D420_SHEET_KEY = "d420-managed"


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setattr(D4, "_INCLUDE_D420_RETURN_SHEET", True, raising=False)


def _contract():
    return parse_contract(D4.build_contract_payload())


def test_d420_in_contract_and_parses():
    assert D420_SHEET_KEY in [s["sheet_key"] for s in D4.build_contract_payload()["sheets"]]
    assert any(s.sheet_key == D420_SHEET_KEY for s in _contract().sheets)


def test_d420_has_four_tables_1_static_3_dynamic():
    sheet = next(s for s in _contract().sheets if s.sheet_key == D420_SHEET_KEY)
    dynamic = [t for t in sheet.tables if t.row_identity is not None]
    static = [t for t in sheet.tables if t.row_identity is None]
    assert len(dynamic) == 3, f"应 3 张动态表，实得 {[t.table_key for t in dynamic]}"
    assert len(static) == 1, "应 1 张 static summary 表"
    assert {t.table_key for t in dynamic} == {R.TABLE_KEY_PROV, R.TABLE_KEY_CUR, R.TABLE_KEY_POST}


def test_d420_dynamic_tables_have_distinct_uuid_cols():
    """3 动态区 UUID 列须互异（同 sheet 多区 alignment 要求）。"""
    raw = D4.build_contract_payload()
    sheet = next(s for s in raw["sheets"] if s["sheet_key"] == D420_SHEET_KEY)
    uuids = {t["table_key"]: t.get("uuid_col") for t in sheet["tables"] if t.get("uuid_col")}
    assert uuids[R.TABLE_KEY_PROV] == "H"
    assert uuids[R.TABLE_KEY_CUR] == "P"
    assert uuids[R.TABLE_KEY_POST] == "Q"
    assert len(set(uuids.values())) == 3


def test_d420_per_region_footer_markers_distinct():
    raw = D4.build_contract_payload()
    sheet = next(s for s in raw["sheets"] if s["sheet_key"] == D420_SHEET_KEY)
    markers = {t["table_key"]: t.get("footer_anchor", {}).get("marker") for t in sheet["tables"] if t.get("footer_anchor")}
    assert markers[R.TABLE_KEY_PROV] == "5.检查本期产品退货情况"
    assert markers[R.TABLE_KEY_CUR] == "6.检查期后产品退货情况"
    assert markers[R.TABLE_KEY_POST] == "检查内容说明："


def test_d420_alignment_ok():
    """3 dynamic 区在共享 entry 下 _align_specs_to_sibling_tables 不抛（uuid 唯一）。"""
    from app.services.workpaper_sync.projection_first_publication import _align_specs_to_sibling_tables
    from app.services.workpaper_sync.phase5_d4_29_customer_detail import row_oriented_sheets

    parsed = _contract()
    sheets = row_oriented_sheets(parsed)
    primary = [t for s in sheets if s.sheet_key == "d42-managed" for t in s.tables if t.row_identity is not None][0]
    pairs = _align_specs_to_sibling_tables(provider=D4, contract=parsed, primary=primary)
    assert len(pairs) >= 1  # 不抛即通过


def test_d420_four_region_roundtrip():
    parsed = _contract()
    payloads = {
        "D4-20-summary": json.dumps([
            {"currentReturn": 100, "currentRevenue": 1000, "priorReturn": 80, "priorRevenue": 900},
            {"currentReturn": 50, "currentRevenue": 500, "priorReturn": 40, "priorRevenue": 450},
        ]),
        "D4-20-provision": json.dumps([{"id": "p1", "productName": "A", "base": 1000, "rate": 0.05, "alreadyProvided": 40, "diffReason": "x"}]),
        "D4-20-current-returns": json.dumps([{"id": "c1", "voucherNo": "V1", "customerName": "甲", "returnAmount": 200, "isAbnormal": "否", "indexRef": "idx"}]),
        "D4-20-post-returns": json.dumps([{"id": "q1", "voucherNo": "V2", "returnAmount": 300, "isAbnormal": "是"}]),
    }
    proj = R.build_store_projection_d420(payloads, contract=parsed)
    merged = R.merge_projection_into_d420_stores(projection=proj, base_by_item={k: json.loads(v) for k, v in payloads.items()})
    assert merged["D4-20-summary"][0]["currentReturn"] == 100
    assert merged["D4-20-summary"][1]["priorRevenue"] == 450
    assert merged["D4-20-provision"][0]["productName"] == "A" and merged["D4-20-provision"][0]["diffReason"] == "x"
    assert merged["D4-20-current-returns"][0]["customerName"] == "甲" and merged["D4-20-current-returns"][0]["indexRef"] == "idx"
    assert merged["D4-20-post-returns"][0]["isAbnormal"] == "是"


def test_d420_dynamic_missing_id_fails_closed():
    parsed = _contract()
    with pytest.raises(ValueError):
        R.build_store_projection_d420({"D4-20-provision": json.dumps([{"productName": "no-id"}])}, contract=parsed)


def test_d420_legacy_nonlist_dynamic_tolerated():
    """非数组 dynamic 载荷视为空（不打挂全 entry）。"""
    parsed = _contract()
    proj = R.build_store_projection_d420({"D4-20-provision": json.dumps({"legacy": True})}, contract=parsed)
    assert proj.row_keys.get(R.TABLE_KEY_PROV, ()) == ()
