# -*- coding: utf-8 -*-
"""D4-13 营业收入账面金额与ERP系统核对记录 守卫。

spec: d-cycle-sheet-bidirectional-expansion · D4-13 paragraph_block_bidirectional（补裁决）
T10 mapping_digest 见 evidence/T10-d413-erp-check-field-mapping.json。

D4-13 全篇（A1:E19）无插删动态行表、无公式（openpyxl 直读核实），走引擎**静态受管区**
路径（`BindingKind.static_region`，同 D4-33/D4-8）：两段自由文本（核对过程/核对结论）
各锚死行号 A6/A16，无 Excel Table、无 UUID 列。此裁决撤销
`d4-inspection-writeback-formula-io/evidence/b1-provider-geometry.md` 对 D4-13 的原
N/A 判定（该判定基于「行表 provider」范式，未评估静态字段直映射路径）。

本守卫钉住：
  1) provider 自洽：mapping_digest 冻结 + sheet_payload 几何正确；
  2) 契约层：live 契约含 D4-13，locator 为静态 definedName_ref + region_kind=static，
     has_dynamic_rows=False（引擎判定走静态路径的判据）；
  3) projection/merge 往返：HTML store 两段中文文本 → 契约投影 → merge 回 store 值一致；
  4) _static_region_bindings 自动为 D4-13 生成 ExcelIdentityBinding（不需手动接线）；
  5) oo_to_html 鸭子类型检测所需的两个名字（merge_d413_fixed_from_projection /
     STORE_ITEM_IDS_D413_FIXED）在主装配模块上确实存在。
"""
from __future__ import annotations

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
import app.services.workpaper_sync.phase5_d4_erp_check_sheet as ERP
from app.services.workpaper_sync.contracts import parse_contract


def _contract():
    return parse_contract(D4.build_contract_payload())


# ── provider 自洽（与 flag 无关，隔离验证几何映射正确） ─────────────────────


def test_mapping_digest_frozen():
    assert ERP.assert_mapping_digest_d413() == ERP.EXPECTED_MAPPING_DIGEST_D413


def test_sheet_payload_shape():
    sp = ERP.sheet_payload_d413()
    assert sp["sheet_key"] == "d413-managed"
    # 静态 locator：definedName_ref + region_kind=static（引擎静态路径，非 Excel Table）
    assert sp["locator"]["anchor"] == "defined_name_ref"
    assert sp["locator"]["defined_name"] == "GT_MANAGED_REGION_D413"
    assert sp["region_boundary_locator"]["region_kind"] == "static"
    table = sp["tables"][0]
    assert table["table_key"] == "d413_erp_check_fixed"
    assert len(table["fields"]) == 2
    cells = {(f["cell"]["column"], f["cell"]["row_from"]) for f in table["fields"]}
    assert ("A", 6) in cells  # 核对过程
    assert ("A", 16) in cells  # 核对结论
    assert all(isinstance(f["cell"]["row_from"], int) for f in table["fields"])
    # 静态表：无 row_identity / delete_policy / footer_anchor（同 D4-5 fixed / D4-33）
    assert "row_identity" not in table
    assert "delete_policy" not in table
    assert "footer_anchor" not in table
    store_items = {f["store_item_id"] for f in table["fields"]}
    assert store_items == {"D4-13-process", "D4-13-conclusion"}


def test_static_sheet_payload_shape():
    sp = ERP.static_sheet_payload_d413()
    assert sp["region_boundary_locator"]["defined_name"] == "GT_MANAGED_REGION_D413"
    assert sp["region_boundary_locator"]["region_kind"] == "static"
    assert sp["tables"][0]["table_key"] == "d413_erp_check_fixed"


# ── projection/merge 纯 Python 往返（同 D4-33 的验证深度：无动态行，不走真实字节
#    materialize，因为静态路径按绝对坐标直写/反读，不需要 identity scan） ──────────


def test_build_projection_and_merge_roundtrip():
    contract = _contract()
    process_text = "已获取ERP系统2025年1-12月营业收入明细，与账面记账凭证逐月核对。"
    conclusion_text = "经核对，账面记录金额与ERP系统记录金额一致，核对结果可接受。"
    payloads = {
        "D4-13-process": process_text,
        "D4-13-conclusion": conclusion_text,
    }
    proj = D4.build_combined_store_projection(payloads, contract=contract)
    pv = proj.get("d413_erp_check_fixed/process")
    cv = proj.get("d413_erp_check_fixed/conclusion")
    assert pv is not None and pv.value == process_text
    assert cv is not None and cv.value == conclusion_text

    base_by_item = {"D4-13-process": "旧核对过程文本", "D4-13-conclusion": "旧核对结论文本"}
    updates = D4.merge_d413_fixed_from_projection(projection=proj, base_by_item=base_by_item)
    assert updates == {"D4-13-process": process_text, "D4-13-conclusion": conclusion_text}


def test_merge_is_no_op_when_unchanged():
    """merge 只返回 touched 字段；值与 base 相同时不产生更新（防止无谓写库）。"""
    contract = _contract()
    text = "核对过程未变"
    payloads = {"D4-13-process": text, "D4-13-conclusion": "结论未变"}
    proj = D4.build_combined_store_projection(payloads, contract=contract)
    base_by_item = {"D4-13-process": text, "D4-13-conclusion": "结论未变"}
    updates = D4.merge_d413_fixed_from_projection(projection=proj, base_by_item=base_by_item)
    assert updates == {}


def test_bytes_payload_decoded_before_projection():
    """oo_to_html 从 DB 读回的 remark 可能是 bytes；确保 build_combined_store_projection
    路径能正确解码（对齐主装配文件里 fixed_payloads 的 bytes 分支处理）。"""
    contract = _contract()
    payloads = {
        "D4-13-process": "字节负载核对过程".encode("utf-8"),
        "D4-13-conclusion": "字节负载核对结论".encode("utf-8"),
    }
    proj = D4.build_combined_store_projection(payloads, contract=contract)
    pv = proj.get("d413_erp_check_fixed/process")
    assert pv is not None and pv.value == "字节负载核对过程"


# ── live 契约落地状态（flag=True，引擎静态 cell 路径已支持） ─────────────────


def test_flag_on_and_present_in_live_contract():
    assert D4._INCLUDE_D413_ERP_CHECK_SHEET is True
    contract = _contract()
    sheet_keys = {s.sheet_key for s in contract.sheets}
    assert "d413-managed" in sheet_keys
    d413_sheet = next(s for s in contract.sheets if s.sheet_key == "d413-managed")
    # D4-13 静态表无动态行（has_dynamic_rows False）——引擎走静态路径的判据（同 D4-33）
    assert all(not t.has_dynamic_rows for t in d413_sheet.tables)


def test_static_region_binding_auto_generated():
    """_static_region_bindings 从 provider 的 static_sheets 声明自动生成 binding
    （不需要手动接线 sibling_bindings，同 D4-33/D4-8）。"""
    from app.services.workpaper_sync.excel_extract import is_static_region
    from app.services.workpaper_sync.projection_first_publication import (
        _static_region_bindings,
    )

    bindings = _static_region_bindings(provider=D4, metadata_sheet="_GT_SYNC")
    d413_bindings = [b for b in bindings if b.table_key == "d413_erp_check_fixed"]
    assert len(d413_bindings) == 1
    binding = d413_bindings[0]
    assert is_static_region(binding) is True
    assert binding.defined_name == "GT_MANAGED_REGION_D413"
    assert binding.table_name == ""
    assert binding.uuid_column == ""


def test_oo_to_html_duck_typing_hooks_present():
    """oo_to_html.py 用 hasattr(bridge, ...) 鸭子类型检测决定是否 mirror D4-13 固定 item；
    确保主装配模块上这两个名字确实存在（否则该 mirror 块永远不会执行，静默不回写）。"""
    assert hasattr(D4, "merge_d413_fixed_from_projection")
    assert hasattr(D4, "STORE_ITEM_IDS_D413_FIXED")
    assert D4.STORE_ITEM_IDS_D413_FIXED == ("D4-13-process", "D4-13-conclusion")


def test_html_store_sibling_registered_in_review_payload():
    """review.html_store.sibling_stores 里必须能找到 D4-13 的登记项（供人工/工具审阅
    契约时能定位到这两个固定字段对应的 checklist_responses item）。"""
    payload = D4.build_contract_payload()
    siblings = payload["review"]["html_store"]["sibling_stores"]
    d413 = [s for s in siblings if s.get("sheet_key") == "d413-managed"]
    assert len(d413) == 1
    assert set(d413[0]["fixed_item_ids"]) == {"D4-13-process", "D4-13-conclusion"}
