# -*- coding: utf-8 -*-
"""D4-34 其他业务收入合同测算表守卫（同 sheet 双动态区 · dict store，2026-09-20 落地）。

引擎支持（有真实动态行维度，区别于 D4-33 纯静态被阻）：2 dynamic 区（房屋租赁 / 咨询业务），
单 dict store D4-34-data（{rentals[],consults[]}），已过 rematerialize（gen68，无 RoundtripEquivalenceError）。

守卫：①契约 parse + 双区几何；②alignment bijection（加 2 dynamic table + 2 spec 后全局仍双射）；
③双区 projection/merge 往返（id/diff 保留、两区不串）；④dict-block 3-tuple 门面；⑤live 契约含 D4-34。
"""
from __future__ import annotations

import json

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
import app.services.workpaper_sync.phase5_d4_other_contract_sheet as C
from app.services.workpaper_sync.contracts import parse_contract


def _contract():
    return parse_contract(D4.build_contract_payload())


def test_sheet_payload_dual_region_shape():
    sp = C.sheet_payload_d434()
    assert sp["sheet_key"] == "d434-managed"
    assert len(sp["tables"]) == 2
    rental = next(t for t in sp["tables"] if t["table_key"] == "d4_34_rentals")
    consult = next(t for t in sp["tables"] if t["table_key"] == "d4_34_consults")
    # 各区动态行：row_identity + delete_policy + footer_anchor + 独立 UUID 列
    for t in (rental, consult):
        assert t["row_identity"] is not None
        assert t["delete_policy"] == "tombstone"
        assert "footer_anchor" in t
    # UUID 列须唯一（同 sheet 双区 alignment 要求）
    assert rental["uuid_col"] == "L"
    assert consult["uuid_col"] == "M"
    assert rental["uuid_col"] != consult["uuid_col"]
    # J 差异 formula_mask（各 5 行）
    assert all(c.startswith("J") for c in rental["formula_mask"])
    assert all(c.startswith("J") for c in consult["formula_mask"])
    # 字段数：rental 9 / consult 8（consult B:C merged，无 period）
    assert len(rental["fields"]) == 9
    assert len(consult["fields"]) == 8


def test_alignment_bijection_holds():
    """加 D4-34 两 dynamic table + 两 spec 后，_align_specs_to_sibling_tables 仍双射（不抛）。"""
    from app.services.workpaper_sync.projection_first_publication import _align_specs_to_sibling_tables
    from app.services.workpaper_sync.phase5_d4_29_customer_detail import row_oriented_sheets

    contract = _contract()
    specs = tuple(D4.instrumentation_specs())
    sheets = row_oriented_sheets(contract)
    total_row_tables = sum(len([t for t in s.tables if t.row_identity is not None]) for s in sheets)
    # 计数守卫：spec 数 == 行 table 总数（数 table 不数 sheet）
    assert len(specs) == total_row_tables
    primary = next(t for s in sheets for t in s.tables if t.row_identity is not None)
    # 不抛 ProviderCapabilityError 即双射成立
    _align_specs_to_sibling_tables(provider=D4, contract=contract, primary=primary)


def test_projection_merge_roundtrip_dual_region():
    contract = _contract()
    store = {
        "rentals": [
            {"id": "rt-a", "tenant": "租户甲", "period": "1-12月", "area": "100", "unitPrice": 50,
             "contractRef": "HT-1", "actualMonths": 12, "expectedRevenue": 600, "actualRevenue": 590,
             "diff": 10, "indexRef": "D4-34-1"},
            {"id": "rt-b", "tenant": "租户乙", "period": "6-12月", "area": "80", "unitPrice": 40,
             "contractRef": "HT-2", "actualMonths": 7, "expectedRevenue": 280, "actualRevenue": 280,
             "diff": 0, "indexRef": ""},
        ],
        "consults": [
            {"id": "cs-x", "client": "委托方X", "project": "尽调", "duration": "3月", "contractAmount": 100,
             "contractRef": "ZX-1", "expectedRevenue": 100, "actualRevenue": 90, "diff": 10, "indexRef": "D4-34-2"},
        ],
    }
    proj = C.build_store_projection_d434(json.dumps(store, ensure_ascii=False), contract=contract)
    # rental 9 字段 × 2 行 + consult 8 字段 × 1 行 = 26
    assert len(proj.values) == 26
    assert proj.row_keys["d4_34_rentals"] == ("rt-a", "rt-b")
    assert proj.row_keys["d4_34_consults"] == ("cs-x",)
    assert proj.get("d4_34_rentals/rt-a/tenant").value == "租户甲"
    assert proj.get("d4_34_consults/cs-x/contract_amount").value == 100

    # merge 回：清空受管字段后应从投影还原
    base = {"rentals": [dict(r) for r in store["rentals"]], "consults": [dict(r) for r in store["consults"]]}
    for r in base["rentals"]:
        r["tenant"] = ""; r["expectedRevenue"] = 0
    for r in base["consults"]:
        r["contractAmount"] = 0
    merged, applied, visited = C.merge_d434_from_projection(
        projection=proj, base_state=json.dumps(base, ensure_ascii=False)
    )
    assert merged["rentals"][0]["tenant"] == "租户甲"
    assert merged["rentals"][0]["expectedRevenue"] == 600
    assert merged["consults"][0]["contractAmount"] == 100
    # id / diff（前端派生）保留，两区不串
    assert merged["rentals"][0]["id"] == "rt-a"
    assert merged["rentals"][0]["diff"] == 10
    assert merged["consults"][0]["id"] == "cs-x"
    assert len(merged["rentals"]) == 2 and len(merged["consults"]) == 1


def test_merge_3tuple_signature():
    contract = _contract()
    proj = C.build_store_projection_d434("{}", contract=contract)
    result = C.merge_d434_from_projection(projection=proj, base_state=None)
    assert isinstance(result, tuple) and len(result) == 3
    merged, applied, visited = result
    assert isinstance(merged, dict) and isinstance(applied, int) and isinstance(visited, int)


def test_live_contract_contains_d434():
    assert D4._INCLUDE_D434_CONTRACT_SHEET is True
    contract = _contract()
    sheet_keys = {s.sheet_key for s in contract.sheets}
    assert "d434-managed" in sheet_keys
    assert hasattr(D4, "STORE_ITEM_ID_D434_DICT")
    assert C.STORE_ITEM_ID_D434 == "D4-34-data"
    assert C.STORE_ITEM_ID_D434 in D4.STORE_ITEM_IDS


def test_missing_or_duplicate_id_raises():
    """行身份缺失/重复 fail-closed（不静默丢数据）；非 list 容差返空。"""
    import pytest

    contract = _contract()
    # 缺 id
    with pytest.raises(ValueError):
        C.build_store_projection_d434(json.dumps({"rentals": [{"tenant": "无id"}], "consults": []}), contract=contract)
    # 重复 id
    with pytest.raises(ValueError):
        C.build_store_projection_d434(
            json.dumps({"rentals": [{"id": "x", "tenant": "a"}, {"id": "x", "tenant": "b"}], "consults": []}),
            contract=contract,
        )
    # 非 list 容差（视为空，不打挂）
    proj = C.build_store_projection_d434(json.dumps({"rentals": "bad", "consults": {}}), contract=contract)
    assert len(proj.values) == 0
