# -*- coding: utf-8 -*-
"""D4-8 重要产品毛利分析表守卫（静态受管区，spec workpaper-sync-static-cell-sheet-writeback）。

census 裁定：D4-8 = 静态块矩阵（无 Excel Table / 无 definedName / 无 UUID / 无动态行，月份固定 1-12
枚举，产品块模板预画）。引擎静态 cell 路径可支持（同 D4-33 分类）。受管 = 产品A(slot0) 12 月 × 12 列
（本期 B/C/D/E/F/G + 上期 J/K/L/M/N/O）+ 同行业 3 行 × 12 列 = 180 static cell；公式列
H/I/P/Q/R/S/T/U/V/W + 合计行 R28 走 formula_mask。第 2+ 产品无模板块 → HTML-only。

本守卫钉住：provider 自洽（契约 parse + projection/merge 往返 slot0 映射）+ live 契约含 D4-8 静态 sheet。
"""
from __future__ import annotations

import json

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
import app.services.workpaper_sync.phase5_d4_product_margin_sheet as M
from app.services.workpaper_sync.contracts import parse_contract


def _isolated_contract():
    """live 契约（flag=True 后 build_contract_payload 已含 D4-8）。"""
    return parse_contract(D4.build_contract_payload())


def _sample_product():
    def month(seed):
        return {"revQty": seed, "revPrice": seed + 1, "revAmt": seed + 2,
                "costQty": seed + 3, "costPrice": seed + 4, "costAmt": seed + 5}
    return {
        "name": "产品A",
        "months": [month(i * 10) for i in range(12)],
        "priorMonths": [month(i * 10 + 100) for i in range(12)],
        "industry": [
            {"name": "同行业A企业", "revQty": 1, "revPrice": 2, "revAmt": 3, "costQty": 4, "costPrice": 5, "costAmt": 6},
            {"name": "同行业B企业", "revQty": 7, "revPrice": 8, "revAmt": 9, "costQty": 10, "costPrice": 11, "costAmt": 12},
            {"name": "行业平均水平", "revQty": 13, "revPrice": 14, "revAmt": 15, "costQty": 16, "costPrice": 17, "costAmt": 18},
        ],
    }


def test_sheet_payload_shape():
    sp = M.sheet_payload_d48()
    assert sp["sheet_key"] == "d48-managed"
    assert sp["locator"]["anchor"] == "defined_name_ref"
    assert sp["locator"]["defined_name"] == "GT_MANAGED_REGION_D48"
    assert sp["region_boundary_locator"]["region_kind"] == "static"
    table = sp["tables"][0]
    assert table["table_key"] == "d4_8_matrix"
    # 12 月 × 6 字段 × 本期/上期(2) + 3 同行业 × 6 × 2 = 144 + 36 = 180
    assert len(table["fields"]) == 180
    assert "row_identity" not in table
    assert "delete_policy" not in table
    # cell 用绝对行号 row_from（int）
    assert all(isinstance(f["cell"]["row_from"], int) for f in table["fields"])
    cells = {(f["cell"]["column"], f["cell"]["row_from"]) for f in table["fields"]}
    assert ("B", 16) in cells  # 1月 本期销量
    assert ("O", 27) in cells  # 12月 上期成本金额
    assert ("B", 29) in cells  # 同行业A 本期销量


def test_projection_merge_roundtrip_slot0():
    contract = _isolated_contract()
    store = [_sample_product(), {"name": "产品B", "months": [], "priorMonths": [], "industry": []}]
    proj = M.build_store_projection_d48(json.dumps(store, ensure_ascii=False), contract=contract)
    assert len(proj.values) == 180
    # 抽验：1月本期销量 = 产品A months[0].revQty = 0（契约键小写 rev_qty，store 键驼峰 revQty）
    assert proj.get("d4_8_matrix/m0_cur/rev_qty").value == 0
    # 12月上期成本金额 = priorMonths[11].costAmt，seed=11*10+100=210，costAmt=seed+5=215
    assert proj.get("d4_8_matrix/m11_prior/cost_amt").value == 215
    # 同行业B 本期单价 = industry[1].revPrice = 8
    assert proj.get("d4_8_matrix/ind1_cur/rev_price").value == 8

    merged, applied, visited = M.merge_d48_from_projection(
        projection=proj, base_state=json.dumps([{"name": "产品A", "months": [], "priorMonths": [], "industry": []}], ensure_ascii=False)
    )
    assert visited == 180
    # 月度 144 + industry cur 18 回写；industry prior 18 不回写（前端无字段）
    assert applied == 144 + 18
    p0 = merged[0]
    for m in range(12):
        assert p0["months"][m]["revQty"] == store[0]["months"][m]["revQty"]
        assert p0["priorMonths"][m]["costAmt"] == store[0]["priorMonths"][m]["costAmt"]
    for i in range(3):
        assert p0["industry"][i]["revPrice"] == store[0]["industry"][i]["revPrice"]


def test_merge_3tuple_signature():
    contract = _isolated_contract()
    proj = M.build_store_projection_d48("[]", contract=contract)
    result = M.merge_d48_from_projection(projection=proj, base_state=None)
    assert isinstance(result, tuple) and len(result) == 3
    merged, applied, visited = result
    assert isinstance(merged, list)
    assert isinstance(applied, int) and isinstance(visited, int)


def test_flag_on_and_present_in_live_contract():
    assert D4._INCLUDE_D48_PRODUCT_MARGIN_SHEET is True
    contract = parse_contract(D4.build_contract_payload())
    sheet_keys = {s.sheet_key for s in contract.sheets}
    assert "d48-managed" in sheet_keys
    d48_sheet = next(s for s in contract.sheets if s.sheet_key == "d48-managed")
    assert all(not t.has_dynamic_rows for t in d48_sheet.tables)
    assert M.STORE_ITEM_ID_D48 == "D4-8-products"
    assert M.STORE_ITEM_ID_D48 in D4.STORE_ITEM_IDS


def test_static_binding_is_static_kind():
    from app.services.workpaper_sync.excel_extract import is_static_region
    binding = M.static_binding_d48()
    assert is_static_region(binding) is True
    assert binding.defined_name == "GT_MANAGED_REGION_D48"
    assert binding.table_name == ""
    assert binding.uuid_column == ""


def test_merge_writes_frontend_camelcase_keys_from_empty_base():
    """🔴 防假绿：projection 的 stable_key 经契约规范化成 snake_case（cost_amt），而前端 store
    是 camelCase（costAmt）。merge 必须把值真实写进**前端 camelCase 键**——否则会写出一套
    snake_case 键，前端读 costAmt 读到空（静默数据丢失，且 base 非空时旧值原样带过会伪装成"往返正确"）。

    判据刻意用**空 base**：base 非空时 merge 空转也能"看起来对"（值是 base 原样带过来的）。
    """
    contract = _isolated_contract()
    src = [_sample_product()]
    proj = M.build_store_projection_d48(json.dumps(src, ensure_ascii=False), contract=contract)
    # projection 侧确实是 snake_case（形态锚点，规范化规则变了这条会先红）
    assert any(k.endswith("/cost_amt") for k in proj.values), sorted(proj.values)[:5]

    empty = [{"name": "A", "months": [], "priorMonths": [], "industry": []}]
    merged, applied, visited = M.merge_d48_from_projection(
        projection=proj, base_state=json.dumps(empty, ensure_ascii=False)
    )
    assert visited == 180
    assert applied == 144 + 18  # 月度全量 + industry cur（prior 前端无字段不回写）
    m0 = merged[0]["months"][0]
    # 前端 camelCase 键必须存在且有值；不得出现 snake_case 键
    for camel in ("revQty", "revPrice", "revAmt", "costQty", "costPrice", "costAmt"):
        assert camel in m0, f"merge 未写前端键 {camel}：实得 {sorted(m0)}"
    for snake in ("rev_qty", "cost_amt"):
        assert snake not in m0, f"merge 写出了 snake_case 键 {snake} —— 前端读不到（静默丢失）"
    assert m0["costAmt"] == src[0]["months"][0]["costAmt"]
    assert merged[0]["priorMonths"][0]["revQty"] == src[0]["priorMonths"][0]["revQty"]
    assert merged[0]["industry"][0]["revPrice"] == src[0]["industry"][0]["revPrice"]
