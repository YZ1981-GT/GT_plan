# -*- coding: utf-8 -*-
"""D4-7 毛利率分析表守卫（同 sheet 1 dynamic + 1 static，2026-09-20 落地 gen76）。

引擎支持：§二产品动态区（当 Excel-Table 载体）+ §一月度静态区（寄生，同 D4-9 totals）。
两 store item（D4-7-products 行数组 + D4-7-monthly 标量对象），已过 rematerialize（gen76，无 drift）。

守卫：①契约 parse + 双区几何（products 有 row_identity / monthly 无）；②alignment bijection
（static 表不计入 spec 数）；③products 动态行 projection/merge 往返（rowId 保留）；④monthly 静态 cell
projection/merge 往返（12 月 + 上期还原）；⑤两区合并投影；⑥live 契约含 D4-7；⑦rowId 缺/重 fail-closed。
"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
import app.services.workpaper_sync.phase5_d4_margin_monthly_sheet as M
from app.services.workpaper_sync.contracts import parse_contract


def _contract():
    return parse_contract(D4.build_contract_payload())


def test_sheet_payload_dynamic_plus_static_shape():
    sp = M.sheet_payload_d47()
    assert sp["sheet_key"] == "d47-managed"
    assert len(sp["tables"]) == 2
    prod = next(t for t in sp["tables"] if t["table_key"] == "d4_7_products")
    monthly = next(t for t in sp["tables"] if t["table_key"] == "d4_7_monthly")
    # §二 products：动态行 + row_identity + delete_policy + footer_anchor + UUID 列
    assert prod["row_identity"] is not None
    assert prod["delete_policy"] == "tombstone"
    assert "footer_anchor" in prod
    assert prod["uuid_col"] == "X"
    assert len(prod["fields"]) == 8  # 8 输入列（派生 15 列进 formula_mask）
    # §一 monthly：静态 cell，无 row_identity / delete_policy / footer_anchor
    assert "row_identity" not in monthly
    assert "delete_policy" not in monthly
    assert "footer_anchor" not in monthly
    assert len(monthly["fields"]) == 26  # revenue[12] + cost[12] + priorRevenue + priorCost
    # 静态 cell 用 static_row（int），非 row_identity
    assert all(isinstance(f["cell"]["row_from"], int) for f in monthly["fields"])


def test_alignment_bijection_holds():
    """§二加 1 dynamic table + 1 spec；§一 static 表不计入 spec 数。全局仍双射。"""
    from app.services.workpaper_sync.projection_first_publication import _align_specs_to_sibling_tables
    from app.services.workpaper_sync.phase5_d4_29_customer_detail import row_oriented_sheets

    contract = _contract()
    specs = tuple(D4.instrumentation_specs())
    sheets = row_oriented_sheets(contract)
    total = sum(len([t for t in s.tables if t.row_identity is not None]) for s in sheets)
    assert len(specs) == total  # 数 dynamic table，不数 static
    primary = next(t for s in sheets for t in s.tables if t.row_identity is not None)
    _align_specs_to_sibling_tables(provider=D4, contract=contract, primary=primary)


def test_products_projection_merge_roundtrip():
    contract = _contract()
    products = [
        {"rowId": "pm-a", "name": "产品甲", "curQty": 100, "curRevenue": 5000, "curCost": 3000,
         "priorQty": 90, "priorRevenue": 4500, "priorCost": 2800, "remark": "主力"},
        {"rowId": "pm-b", "name": "产品乙", "curQty": 50, "curRevenue": 2000, "curCost": 1500,
         "priorQty": 40, "priorRevenue": 1800, "priorCost": 1300, "remark": ""},
    ]
    payloads = {
        M.STORE_ITEM_ID_D47_PRODUCTS: json.dumps(products, ensure_ascii=False),
        M.STORE_ITEM_ID_D47_MONTHLY: "{}",
    }
    proj = M.build_store_projection_d47(payloads, contract=contract)
    assert proj.row_keys["d4_7_products"] == ("pm-a", "pm-b")
    assert proj.get("d4_7_products/pm-a/cur_revenue").value == 5000
    assert proj.get("d4_7_products/pm-b/name").value == "产品乙"

    base = [dict(r) for r in products]
    for r in base:
        r["curRevenue"] = 0; r["name"] = ""
    merged = M.merge_projection_into_products(
        projection=proj, base_payload=json.dumps(base, ensure_ascii=False)
    )
    assert merged[0]["curRevenue"] == 5000
    assert merged[0]["name"] == "产品甲"
    assert merged[0]["rowId"] == "pm-a"  # 行身份保留
    assert merged[1]["rowId"] == "pm-b"
    assert len(merged) == 2


def test_monthly_projection_merge_roundtrip():
    contract = _contract()
    monthly = {"revenue": [i * 100 for i in range(1, 13)], "cost": [i * 60 for i in range(1, 13)],
               "priorRevenue": 7000, "priorCost": 4500}
    payloads = {
        M.STORE_ITEM_ID_D47_PRODUCTS: "[]",
        M.STORE_ITEM_ID_D47_MONTHLY: json.dumps(monthly, ensure_ascii=False),
    }
    proj = M.build_store_projection_d47(payloads, contract=contract)
    assert proj.get("d4_7_monthly/revenue_0").value == 100
    assert proj.get("d4_7_monthly/revenue_11").value == 1200
    assert proj.get("d4_7_monthly/cost_0").value == 60
    assert proj.get("d4_7_monthly/prior_revenue").value == 7000
    assert proj.get("d4_7_monthly/prior_cost").value == 4500

    base = {"revenue": [0] * 12, "cost": [0] * 12, "priorRevenue": 0, "priorCost": 0}
    merged = M.merge_projection_into_monthly(
        projection=proj, base_payload=json.dumps(base, ensure_ascii=False)
    )
    assert merged["revenue"] == [i * 100 for i in range(1, 13)]
    assert merged["cost"] == [i * 60 for i in range(1, 13)]
    assert merged["priorRevenue"] == 7000
    assert merged["priorCost"] == 4500


def test_combined_two_region_projection_value_count():
    contract = _contract()
    products = [
        {"rowId": "pm-a", "name": "甲", "curQty": 1, "curRevenue": 2, "curCost": 3,
         "priorQty": 4, "priorRevenue": 5, "priorCost": 6, "remark": "r"},
    ]
    monthly = {"revenue": [1] * 12, "cost": [1] * 12, "priorRevenue": 1, "priorCost": 1}
    proj = M.build_store_projection_d47(
        {
            M.STORE_ITEM_ID_D47_PRODUCTS: json.dumps(products, ensure_ascii=False),
            M.STORE_ITEM_ID_D47_MONTHLY: json.dumps(monthly, ensure_ascii=False),
        },
        contract=contract,
    )
    # products 8 字段 × 1 行 + monthly 26 cell = 34
    assert len(proj.values) == 34


def test_live_contract_contains_d47():
    assert D4._INCLUDE_D47_MARGIN_SHEET is True
    contract = _contract()
    sheet_keys = {s.sheet_key for s in contract.sheets}
    assert "d47-managed" in sheet_keys
    assert hasattr(D4, "STORE_ITEM_IDS_D47_DEDICATED")
    assert M.STORE_ITEM_ID_D47_PRODUCTS == "D4-7-products"
    assert M.STORE_ITEM_ID_D47_MONTHLY == "D4-7-monthly"
    assert M.STORE_ITEM_ID_D47_PRODUCTS in D4.STORE_ITEM_IDS
    assert M.STORE_ITEM_ID_D47_MONTHLY in D4.STORE_ITEM_IDS


def test_products_missing_or_duplicate_rowid_raises():
    """行身份缺失/重复 fail-closed（禁数组下标当身份）；非 list 容差返空。"""
    contract = _contract()
    with pytest.raises(ValueError):
        M.build_products_projection(json.dumps([{"name": "无rowId"}]), contract=contract)
    with pytest.raises(ValueError):
        M.build_products_projection(
            json.dumps([{"rowId": "x", "name": "a"}, {"rowId": "x", "name": "b"}]), contract=contract
        )
    proj = M.build_products_projection(json.dumps("bad"), contract=contract)
    assert len(proj.values) == 0
