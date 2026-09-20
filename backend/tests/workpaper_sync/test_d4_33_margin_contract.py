# -*- coding: utf-8 -*-
"""D4-33 其他业务毛利率分析表守卫。

裁定（2026-09-20）：引擎**不支持纯静态 cell sheet 双向回写** —— 受管 cell 只能经
ExcelIdentityBinding 落盘，而 binding 必须锚定一张 row_identity 动态表的 Excel Table
`<tableParts>` 载体（materialize.managed_tables_of 对无动态行的 sheet 直接 raise）。
D4-33 整张只有 12 月 × 3 业务类型的 static cell、**无任何动态行维度**，故当前 **HTML-only**
（`_INCLUDE_D433_MARGIN_SHEET=False`，同 D4-45 静态块 precedent）。

本守卫钉住两件事：
  1) provider 自洽：契约 parse + 72 cell projection/merge 往返（slot 位置映射）全绿 ——
     引擎解锁后可一键翻 flag=True 接入，provider 不需重写；
  2) 当前 live 契约**不含** D4-33（flag=False 的诚实状态），且 STORE_ITEM_ID_D433_DICT
     未导出（oo_to_html 专用块 inert，不会对未进契约的 D4-33 空投影误写）。
"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
import app.services.workpaper_sync.phase5_d4_other_margin_sheet as M
from app.services.workpaper_sync.contracts import parse_contract


# ── provider 自洽（与 flag 无关，隔离验证几何映射正确） ─────────────────────


def _isolated_contract():
    """把 D4-33 单 sheet 塞进全量契约的一个拷贝里 parse（不改 live flag）。"""
    payload = D4.build_contract_payload()
    payload = dict(payload)
    payload["sheets"] = list(payload["sheets"]) + [M.sheet_payload_d433()]
    return parse_contract(payload)


def test_sheet_payload_shape():
    sp = M.sheet_payload_d433()
    assert sp["sheet_key"] == "d433-managed"
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


# ── live 契约诚实状态（flag=False，引擎不支持纯静态 sheet） ─────────────────


def test_flag_off_and_absent_from_live_contract():
    # 裁定：引擎不支持纯静态 cell sheet → 当前 HTML-only
    assert D4._INCLUDE_D433_MARGIN_SHEET is False
    contract = parse_contract(D4.build_contract_payload())
    sheet_keys = {s.sheet_key for s in contract.sheets}
    assert "d433-managed" not in sheet_keys
    # STORE_ITEM_ID_D433_DICT 未导出 → oo_to_html 专用块 inert
    assert not hasattr(D4, "STORE_ITEM_ID_D433_DICT")
    # 但 store item id 常量本身仍在（前端/store 用），只是不进 STORE_ITEMS
    assert M.STORE_ITEM_ID_D433 == "D4-33-data"
    assert M.STORE_ITEM_ID_D433 not in D4.STORE_ITEM_IDS
