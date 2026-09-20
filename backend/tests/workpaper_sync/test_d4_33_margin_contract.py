# -*- coding: utf-8 -*-
"""D4-33 其他业务毛利率分析表守卫。

✅ 落地（spec workpaper-sync-static-cell-sheet-writeback，2026-09-20）：引擎新增
definedName 锚定**静态受管区**路径（`BindingKind.static_region`），D4-33 从 HTML-only
转为真双向。静态 binding 用 `defined_name=GT_MANAGED_REGION_D433`（无 table_name/uuid_column），
锚点是 workbook-scope definedName（instrumentation 注入）；extract/materialize 跳过
identity scan / row_shift / footer / minted UUID，按绝对坐标直写/反读。

本守卫钉住：
  1) provider 自洽：契约 parse + 72 cell projection/merge 往返（slot 位置映射）全绿；
  2) live 契约**含** D4-33（`_INCLUDE_D433_MARGIN_SHEET=True`），sheet locator 为静态
     definedName_ref + region_kind=static，且 STORE_ITEM_ID_D433_DICT 已导出。
"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
import app.services.workpaper_sync.phase5_d4_other_margin_sheet as M
from app.services.workpaper_sync.contracts import parse_contract


# ── provider 自洽（与 flag 无关，隔离验证几何映射正确） ─────────────────────


def _isolated_contract():
    """live 契约（flag=True 后 build_contract_payload 已含 D4-33）。"""
    return parse_contract(D4.build_contract_payload())


def test_sheet_payload_shape():
    sp = M.sheet_payload_d433()
    assert sp["sheet_key"] == "d433-managed"
    # 静态 locator：definedName_ref + region_kind=static（引擎静态路径，非 Excel Table）
    assert sp["locator"]["anchor"] == "defined_name_ref"
    assert sp["locator"]["defined_name"] == "GT_MANAGED_REGION_D433"
    assert sp["region_boundary_locator"]["region_kind"] == "static"
    table = sp["tables"][0]
    assert table["table_key"] == "d4_33_matrix"
    # 前 3 业务类型 × 12 月 × 收入/成本 = 72 static cell
    assert len(table["fields"]) == 72
    # 静态表：无 row_identity / delete_policy / footer_anchor
    assert "row_identity" not in table
    assert "delete_policy" not in table
    assert "footer_anchor" not in table
    # cell 用绝对行号 row_from（int），非 row_identity
    cells = {(f["cell"]["column"], f["cell"]["row_from"]) for f in table["fields"]}
    assert ("E", 12) in cells  # slot0 1月 收入
    assert ("L", 23) in cells  # slot2 12月 成本
    assert all(isinstance(f["cell"]["row_from"], int) for f in table["fields"])


def test_projection_merge_roundtrip_first3_slots():
    contract = _isolated_contract()
    store = {
        "bizTypes": [
            {"id": "biz-rent-fixed", "name": "出租固定资产"},
            {"id": "biz-rent-intangible", "name": "出租无形资产"},
            {"id": "biz-sell-material", "name": "销售材料"},
            {"id": "biz-extra", "name": "第四类"},  # 无模板列 → HTML-only，不受管
        ],
        "months": {
            "biz-rent-fixed": [{"revenue": (i + 1) * 100, "cost": (i + 1) * 60} for i in range(12)],
            "biz-rent-intangible": [{"revenue": (i + 1) * 10, "cost": (i + 1) * 4} for i in range(12)],
            "biz-sell-material": [{"revenue": (i + 1) * 5, "cost": (i + 1) * 2} for i in range(12)],
            "biz-extra": [{"revenue": 999, "cost": 999} for _ in range(12)],
        },
        "priorYear": {"biz-rent-fixed": {"revenue": 1, "cost": 1}},
    }
    proj = M.build_store_projection_d433(json.dumps(store, ensure_ascii=False), contract=contract)
    assert len(proj.values) == 72
    assert proj.get("d4_33_matrix/slot0_m0/revenue").value == 100
    assert proj.get("d4_33_matrix/slot2_m11/cost").value == 24  # (11+1)*2

    base = {"bizTypes": store["bizTypes"], "months": {}, "priorYear": {}}
    merged, applied, visited = M.merge_d433_from_projection(
        projection=proj, base_state=json.dumps(base, ensure_ascii=False)
    )
    assert visited == 72
    assert applied == 72
    for bid in ("biz-rent-fixed", "biz-rent-intangible", "biz-sell-material"):
        for mo in range(12):
            for fld in ("revenue", "cost"):
                assert merged["months"][bid][mo][fld] == store["months"][bid][mo][fld]
    # 第 4 类无模板列 → 不进受管 store.months（base 未含它，merge 只碰前 3 slot）
    assert "biz-extra" not in merged["months"]
    # bizTypes / priorYear 保留
    assert len(merged["bizTypes"]) == 4


def test_merge_3tuple_signature_for_dict_block():
    """dict store 门面返 (merged_dict, applied, visited) 3-tuple（同 D4-9/D4-35 oo_to_html 块约定）。"""
    contract = _isolated_contract()
    proj = M.build_store_projection_d433("{}", contract=contract)
    result = M.merge_d433_from_projection(projection=proj, base_state=None)
    assert isinstance(result, tuple) and len(result) == 3
    merged, applied, visited = result
    assert isinstance(merged, dict)
    assert isinstance(applied, int) and isinstance(visited, int)


# ── live 契约落地状态（flag=True，引擎静态 cell 路径已支持） ─────────────────


def test_flag_on_and_present_in_live_contract():
    # 落地：引擎静态 cell 路径支持 → D4-33 真双向
    assert D4._INCLUDE_D433_MARGIN_SHEET is True
    contract = parse_contract(D4.build_contract_payload())
    sheet_keys = {s.sheet_key for s in contract.sheets}
    assert "d433-managed" in sheet_keys
    # D4-33 静态表无动态行（has_dynamic_rows False）——引擎走静态路径的判据
    d433_sheet = next(s for s in contract.sheets if s.sheet_key == "d433-managed")
    assert all(not t.has_dynamic_rows for t in d433_sheet.tables)
    # STORE_ITEM_ID_D433_DICT 已导出 → oo_to_html 专用 dict 块生效
    assert hasattr(D4, "STORE_ITEM_ID_D433_DICT")
    assert D4.STORE_ITEM_ID_D433_DICT == "D4-33-data"
    # store item id 进 STORE_ITEM_IDS（combined projection）
    assert M.STORE_ITEM_ID_D433 == "D4-33-data"
    assert M.STORE_ITEM_ID_D433 in D4.STORE_ITEM_IDS


def test_static_binding_is_static_kind():
    from app.services.workpaper_sync.excel_extract import is_static_region

    binding = M.static_binding_d433()
    assert is_static_region(binding) is True
    assert binding.defined_name == "GT_MANAGED_REGION_D433"
    assert binding.table_name == ""
    assert binding.uuid_column == ""
