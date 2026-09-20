# -*- coding: utf-8 -*-
"""D4-12 合同检查表守卫（转置表，spec d4-12-transposed-writeback / Requirement 3.5, 3.6 / Property 4）。

D4-12 = 转置动态表（一列=一份合同，一行=一个字段；首列 B、21 字段 R11-R31、GT-CONTRACT- 载体）。
走泛化通用引擎 phase5_transposed_sheet + 注册表分派。本守卫钉住：
- SPEC_D412 几何/身份/store 形态正确（首列 B 非 C、扁平 store、21 字段）；
- sheet_payload 转置形态（layout=customer_columns / transposed_columns / 21 field transposed_row）；
- mapping_digest 冻结；
- flag on 后 live 契约含 d4-12-managed 且 parse 通过、不打挂同 entry 其它张；
- store item 登记齐全。
"""
from __future__ import annotations

import pytest

import app.services.workpaper_sync.phase5_d4_revenue_detail as D4
import app.services.workpaper_sync.phase5_d4_12_contract as D12
from app.services.workpaper_sync.contracts import parse_contract


def _live_contract():
    """flag=True 后 build_contract_payload 已含 D4-12。"""
    return parse_contract(D4.build_contract_payload())


def test_spec_geometry():
    s = D12.SPEC_D412
    assert s.sheet_key == "d4-12-managed"
    assert s.table_key == "contract_inspection_transposed"
    assert s.store_item_id == "D4-12-contracts-v2"
    assert s.header_row == 10
    assert s.first_entity_column == "B"  # DEC-4: 首列 B 非 C
    assert s.initial_entity_column == "K"
    assert s.identity_carrier_prefix == "GT-CONTRACT-"
    assert s.defined_name == "GT_MANAGED_REGION_D412"
    assert s.managed_ref == "$B$10:$K$31"
    # 扁平 store（无 fields 嵌套 / header 非受管字段）
    assert s.header_field_key is None
    assert s.nested_fields_key is None
    # 21 字段 R11-R31 连续
    assert len(s.field_rows) == 21
    assert tuple(s.field_rows.values()) == tuple(range(11, 32))
    # 合同金额数值语义
    assert "contractamount" in s.numeric_fields


def test_sheet_payload_transposed_shape():
    sp = D12.sheet_payload()
    assert sp["sheet_key"] == "d4-12-managed"
    assert sp["template_id"] == "D412"
    assert sp["locator"]["anchor"] == "defined_name_ref"
    assert sp["locator"]["defined_name"] == "GT_MANAGED_REGION_D412"
    table = sp["tables"][0]
    assert table["table_key"] == "contract_inspection_transposed"
    assert table["layout"] == "customer_columns"  # 转置 layout
    assert table["delete_policy"] == "tombstone"
    tc = table["transposed_columns"]
    assert tc["identity_prefix"] == "GT-CONTRACT-"
    assert tc["identity"] == "id"
    # 21 字段各带 transposed_row（R11-R31），首实体列 B
    fields = table["fields"]
    assert len(fields) == 21
    rows = sorted(f["transposed_row"] for f in fields)
    assert rows == list(range(11, 32))
    assert all(f["cell"]["column"] == "B" for f in fields)
    # 合同金额 value_type=amount（ValueType 枚举无 number）
    amt = next(f for f in fields if f["stable_field_key"].endswith("/contractamount"))
    assert amt["value_type"] == "amount"


def test_mapping_digest_frozen():
    assert D12.compute_mapping_digest() == D12.EXPECTED_MAPPING_DIGEST
    assert D12.EXPECTED_MAPPING_DIGEST == (
        "2d3a1c5f77f198283603ac42b4eb54f5d67ef2f4dfa7aa57a2673a023c689e9a"
    )


def test_flag_on_and_present_in_live_contract():
    assert D4._INCLUDE_D412_TRANSPOSED is True
    contract = _live_contract()
    sheet_keys = {s.sheet_key for s in contract.sheets}
    assert "d4-12-managed" in sheet_keys
    assert D12.STORE_ITEM_ID == "D4-12-contracts-v2"
    assert D12.STORE_ITEM_ID in D4.STORE_ITEM_IDS


def test_live_contract_does_not_break_sibling_sheets():
    """加 D4-12 后同 entry 其它转置/行表 sheet 仍在契约中（不打挂）。"""
    contract = _live_contract()
    sheet_keys = {s.sheet_key for s in contract.sheets}
    for other in ("d42-managed", "d43-managed", "d4-29-managed"):
        assert other in sheet_keys, f"D4-12 加入后 {other} 从契约消失"


def test_stable_key_and_pointer_root():
    # stable_key = contract_inspection_transposed/{id}/{field}
    assert D12.stable_key_for("c-0", "contractNo") == "contract_inspection_transposed/c-0/contractno"
    sp = D12.sheet_payload()
    # json_pointer 根用 contracts（pointer_root），不是 table_key
    ptr = sp["tables"][0]["fields"][0]["json_pointer"]
    assert ptr.startswith("/contracts/{row_uuid}/")
    # row_identity pointer 同根
    assert sp["tables"][0]["row_identity"]["json_pointer"] == "/contracts/*/id"
