# -*- coding: utf-8 -*-
"""D2-3 坏账准备明细表契约 + store 投影/合并/身份 —— 行为级判据（judge-first）。

spec: d2-sync-coverage-via-row-table-engine · Task 3/6/7/8
Requirements 1.1/1.2/1.3/1.4/1.5/1.6/1.7 · design Property 3/4/4b

架构：D2-3 作为 gt-d2-accounts-receivable 的 sibling sheet（d23-managed，adapter
d2.receivable_detail）。契约经**父 pilot** pilot_d2_large_json.build_contract_payload()
的 sheets[] 纳入，parse_contract 强校验；投影/合并由 sibling provider phase5_d2_03_bad_debt。

🔴 实测反转 spec 裁决 E2（见 evidence/T03）：模板只有 **2 物理段**（单项/组合），不是 spec 说
的 3 段。3 store 键（individual/aging/customer-type）→ 2 物理区（个别键→单项区；aging+
customer-type→组合区，行内 category 分流）。binding **1→3**（D2-2 ① + D2-3 ②），不是 1→4。

判据（parse_contract 真跑，非符号存在）：
- Q3：D2-3 formula_mask ≡ E/K/N 三列 × 数据行区间，引擎现算不手写
- Q4：D2-3 是 2 受管区，全 entry binding 1→3；两区 UUID 列不同
- Q4b：3 store 键回写后各自读回等值（下游 5 处消费方靠此不缺一类）
"""
from __future__ import annotations

import json

import pytest

from app.services.workpaper_sync import phase5_d2_03_bad_debt as m
from app.services.workpaper_sync import pilot_d2_large_json as parent
from app.services.workpaper_sync.contracts import FieldMode, parse_contract


@pytest.fixture(scope="module")
def contract():
    return parse_contract(parent.build_contract_payload(), adapter_id=parent.PILOT_ADAPTER_ID)


@pytest.fixture(scope="module")
def sheet(contract):
    by_key = {s.sheet_key: s for s in contract.sheets}
    assert m.SHEET_KEY_D23 in by_key, "父契约缺 D2-3 sibling sheet d23-managed"
    return by_key[m.SHEET_KEY_D23]


# ═══════════════════════════════════════════════════════════════════════════
# Q4：D2-3 是 2 受管区，binding 1→3，两区 UUID 列不同
# ═══════════════════════════════════════════════════════════════════════════
def test_d23_sheet_has_exactly_two_regions(sheet) -> None:
    keys = [t.table_key for t in sheet.tables]
    assert keys == [
        m.ROWS_TABLE_KEY_INDIVIDUAL,
        m.ROWS_TABLE_KEY_COMBINED,
    ], f"D2-3 必须是 2 受管区（实测模板 2 物理段），实得 {keys}"


def test_total_binding_count_is_three(contract) -> None:
    """全 entry 受管区数 = D2-2 ① + D2-3 ② = 3（binding 1→3）。"""
    total = sum(len(s.tables) for s in contract.sheets)
    assert total == 3, f"扩容后受管区数应为 3（1→3），实得 {total}"


def test_two_regions_use_distinct_uuid_columns() -> None:
    assert m.UUID_COL_INDIVIDUAL != m.UUID_COL_COMBINED
    assert m.UUID_COL_INDIVIDUAL == "O"
    assert m.UUID_COL_COMBINED == "P"


def test_both_regions_have_row_identity_and_delete_policy(sheet) -> None:
    for t in sheet.tables:
        assert t.row_identity is not None, f"{t.table_key} 缺 row_identity"
        assert t.delete_policy is not None, f"{t.table_key} 缺 delete_policy"


# ═══════════════════════════════════════════════════════════════════════════
# Q3：formula_mask ≡ E/K/N 三列 × 数据行区间（引擎现算不手写）
# ═══════════════════════════════════════════════════════════════════════════
def test_formula_columns_are_e_k_n(sheet) -> None:
    by_key = {t.table_key: t for t in sheet.tables}
    for tk in (m.ROWS_TABLE_KEY_INDIVIDUAL, m.ROWS_TABLE_KEY_COMBINED):
        t = by_key[tk]
        formula_fields = [f for f in t.fields if f.mode is FieldMode.formula]
        cols = sorted(f.column_key for f in formula_fields)
        assert cols == ["current_audited", "current_unadjusted", "prior_audited"], cols
        # 三列各在 mask 里出现
        for col in m.FORMULA_COLUMNS:
            assert any(rng.startswith(f"{col}") for rng in t.formula_mask), (tk, col, t.formula_mask)


def test_formula_mask_matches_data_row_ranges() -> None:
    """mask 由 _region_formula_mask 现算，等于 E/K/N × [小计行, 末数据行]。"""
    assert m.FORMULA_MASK_INDIVIDUAL == ("E12:E16", "K12:K16", "N12:N16")
    assert m.FORMULA_MASK_COMBINED == ("E17:E21", "K17:K21", "N17:N21")


def test_managed_data_columns_never_in_mask(sheet) -> None:
    """受管数据行的 B/C/D/F/G/H/I/J/L/M 绝不入 mask（否则被误判只读）。"""
    by_key = {t.table_key: t for t in sheet.tables}
    editable_cols = {"B", "C", "D", "F", "G", "H", "I", "J", "L", "M"}
    for tk in (m.ROWS_TABLE_KEY_INDIVIDUAL, m.ROWS_TABLE_KEY_COMBINED):
        t = by_key[tk]
        for rng in t.formula_mask:
            col = rng.split(":")[0].rstrip("0123456789")
            assert col not in editable_cols, f"{tk} 的 mask {rng} 命中了可编辑列 {col}"


# ═══════════════════════════════════════════════════════════════════════════
# Q4b：3 store 键 → 2 区投影 + 回写各自读回等值（下游 5 处消费方不缺一类）
# ═══════════════════════════════════════════════════════════════════════════
def _stores(ind_rows, aging_rows, cust_rows):
    return {
        m.STORE_ITEM_ID_INDIVIDUAL: json.dumps(ind_rows),
        m.STORE_ITEM_ID_AGING: json.dumps(aging_rows),
        m.STORE_ITEM_ID_CUSTOMER: json.dumps(cust_rows),
    }


def _sub(rid, category=None, **vals):
    row = {"rowId": rid, "isSubRow": True, "isFixed": False}
    if category:
        row["category"] = category
    row.update(vals)
    return row


def _fixed(rid):
    return {"rowId": rid, "isSubRow": False, "isFixed": True}


def test_projection_splits_three_keys_into_two_regions(contract) -> None:
    payloads = _stores(
        [_sub("i1", priorUnadjusted=100), _fixed("fixed-individual")],
        [_sub("a1", "aging", priorUnadjusted=200), _fixed("fixed-aging")],
        [_sub("c1", "customer-type", priorUnadjusted=300)],
    )
    proj = m.build_d23_store_projection(payloads, contract=contract)
    assert proj.row_keys[m.ROWS_TABLE_KEY_INDIVIDUAL] == ("i1",)
    assert set(proj.row_keys[m.ROWS_TABLE_KEY_COMBINED]) == {"a1", "c1"}
    # summary 行（fixed-*）不落投影
    keys = [str(k) for k in proj.stable_keys()]
    assert not any("fixed-" in k for k in keys)


def test_summary_rows_excluded_from_projection(contract) -> None:
    """isFixed 分类小计行 + 合计行 → rowType=summary，computed 不落库。"""
    assert m.row_type_for(_fixed("fixed-individual")) == "summary"
    assert m.row_type_for({"rowId": "__total__"}) == "summary"
    assert m.row_type_for(_sub("i1")) == "dynamic"


def test_missing_row_id_fails_closed(contract) -> None:
    payloads = _stores([_sub(None, priorUnadjusted=1) | {"rowId": ""}], [], [])
    with pytest.raises(m.StorePayloadError):
        m.build_d23_store_projection(payloads, contract=contract)


def test_duplicate_row_id_in_region_fails_closed(contract) -> None:
    payloads = _stores([_sub("dup"), _sub("dup")], [], [])
    with pytest.raises(m.StorePayloadError):
        m.build_d23_store_projection(payloads, contract=contract)


def test_cross_key_duplicate_in_combined_region_fails_closed(contract) -> None:
    """aging 与 customer-type 在同一物理区 ⇒ rowId 必须全局唯一（避免物理行串区）。"""
    payloads = _stores([], [_sub("x", "aging")], [_sub("x", "customer-type")])
    with pytest.raises(m.StorePayloadError):
        m.build_d23_store_projection(payloads, contract=contract)


def test_roundtrip_three_keys_each_read_back_equal(contract) -> None:
    """Q4b：投影→合并后，三键各自读回等值，组合区按 category 归属键分流回 aging/customer。"""
    payloads = _stores(
        [_sub("i1", priorUnadjusted=100, currentProvision=50)],
        [_sub("a1", "aging", priorUnadjusted=200)],
        [_sub("c1", "customer-type", priorUnadjusted=300)],
    )
    proj = m.build_d23_store_projection(payloads, contract=contract)
    merged, applied, visited, touched = m.merge_projection_into_d23_stores(
        projection=proj,
        base_states={k: json.loads(v) for k, v in payloads.items()},
    )
    # 三键各自读回：individual→i1；组合区 a1 回 aging、c1 回 customer-type
    ind_ids = [r["rowId"] for r in merged[m.STORE_ITEM_ID_INDIVIDUAL]]
    aging_ids = [r["rowId"] for r in merged[m.STORE_ITEM_ID_AGING]]
    cust_ids = [r["rowId"] for r in merged[m.STORE_ITEM_ID_CUSTOMER]]
    assert ind_ids == ["i1"]
    assert aging_ids == ["a1"]
    assert cust_ids == ["c1"]
    # 值等值
    assert merged[m.STORE_ITEM_ID_INDIVIDUAL][0]["priorUnadjusted"] == 100
    assert merged[m.STORE_ITEM_ID_AGING][0]["priorUnadjusted"] == 200
    assert merged[m.STORE_ITEM_ID_CUSTOMER][0]["priorUnadjusted"] == 300


# ═══════════════════════════════════════════════════════════════════════════
# mapping_digest + 契约双向锁
# ═══════════════════════════════════════════════════════════════════════════
def test_mapping_digest_stable() -> None:
    assert m.assert_mapping_digest_d23() == m.EXPECTED_MAPPING_DIGEST_D23


def test_parent_contract_disk_source_locked() -> None:
    """父契约（含 D2-3 sibling sheet）磁盘 ↔ 现算 payload 双向锁死。"""
    parent.assert_contract_file_matches_source()
