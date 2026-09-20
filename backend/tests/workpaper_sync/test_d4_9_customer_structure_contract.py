# -*- coding: utf-8 -*-
"""D4-9 契约结构 + store 投影/合并/身份 —— 行为级验证（judge-first）。

spec: d4-9-customer-structure-bidirectional-writeback · Task 3/4
Requirements 2.1/2.2/2.3/2.4/2.5 · 3.1/3.3/3.4 · 4.2 · Property 1/3/4

架构（路 B）：D4-9 作为 gt-d4-operating-revenue 的 sibling sheet（d49-managed，
adapter d4.revenue_detail）。契约经**父模块** phase5_d4_revenue_detail.build_contract_payload()
的 sheets[] 纳入，parse_contract 强校验；投影/合并由 sibling provider
phase5_d4_customer_structure 提供。

判据（parse_contract 真跑，非符号存在）：
1. 父契约含 sheet d49-managed，恰 3 张 table（current/prior/totals）；前两张有
   row_identity + delete_policy，第三张无 row_identity 且 4 字段 row_scoped=False 带
   static_row（24/38）。
2. D/F 占比字段 mode=formula 且列落各自 table 的 formula_mask；合计行 footer
   carries_total_formula=true。
3. store 投影：current/prior 各区 rowId 独立唯一；缺/重复 rowId fail-closed；
   totals 静态标量 row_key=None。
4. 投影→合并 roundtrip：current/prior 行与 4 总额逐字段还原，两区不串。
"""
from __future__ import annotations

import json

import pytest

from app.services.workpaper_sync import phase5_d4_customer_structure as m
from app.services.workpaper_sync import phase5_d4_revenue_detail as parent
from app.services.workpaper_sync.contracts import FieldMode, parse_contract


@pytest.fixture(scope="module")
def contract():
    return parse_contract(parent.build_contract_payload(), adapter_id=parent.ADAPTER_ID)


@pytest.fixture(scope="module")
def sheet(contract):
    by_key = {s.sheet_key: s for s in contract.sheets}
    assert m.SHEET_KEY_D49 in by_key, "父契约缺 D4-9 sibling sheet d49-managed"
    return by_key[m.SHEET_KEY_D49]


# ═══════════════════════════════════════════════════════════════════════════
# 判据 1：D4-9 sheet 三 table 结构
# ═══════════════════════════════════════════════════════════════════════════
def test_d49_sheet_has_exactly_three_tables(sheet) -> None:
    keys = [t.table_key for t in sheet.tables]
    assert keys == [
        m.ROWS_TABLE_KEY_CURRENT,
        m.ROWS_TABLE_KEY_PRIOR,
        m.TOTALS_TABLE_KEY,
    ], f"D4-9 必须是三 table，实得 {keys}"


def test_dynamic_tables_have_row_identity_and_delete_policy(sheet) -> None:
    by_key = {t.table_key: t for t in sheet.tables}
    for tk in (m.ROWS_TABLE_KEY_CURRENT, m.ROWS_TABLE_KEY_PRIOR):
        t = by_key[tk]
        assert t.row_identity is not None, f"{tk} 缺 row_identity"
        assert t.delete_policy is not None, f"{tk} 缺 delete_policy"


def test_totals_table_is_static_scalars_no_row_identity(sheet) -> None:
    totals = {t.table_key: t for t in sheet.tables}[m.TOTALS_TABLE_KEY]
    assert totals.row_identity is None
    assert totals.delete_policy is None
    assert len(totals.fields) == 4
    static_rows = sorted(f.cell.static_row for f in totals.fields)
    assert static_rows == [24, 24, 38, 38], f"totals 静态行应为 24/24/38/38，实得 {static_rows}"
    for f in totals.fields:
        assert f.row_scoped is False
        assert "{row_uuid}" not in f.json_pointer


def test_two_regions_use_distinct_uuid_columns() -> None:
    assert m.UUID_COL_CURRENT != m.UUID_COL_PRIOR


# ═══════════════════════════════════════════════════════════════════════════
# 判据 2：占比 formula + formula_mask + footer carries_total_formula
# ═══════════════════════════════════════════════════════════════════════════
def test_ratio_columns_are_formula_and_masked(sheet) -> None:
    by_key = {t.table_key: t for t in sheet.tables}
    for tk in (m.ROWS_TABLE_KEY_CURRENT, m.ROWS_TABLE_KEY_PRIOR):
        t = by_key[tk]
        ratio_fields = [f for f in t.fields if f.column_key in ("amount_ratio", "quantity_ratio")]
        assert len(ratio_fields) == 2
        for f in ratio_fields:
            assert f.mode is FieldMode.formula
        assert any("D" in rng for rng in t.formula_mask)
        assert any("F" in rng for rng in t.formula_mask)


def test_footer_carries_total_formula(sheet) -> None:
    by_key = {t.table_key: t for t in sheet.tables}
    for tk in (m.ROWS_TABLE_KEY_CURRENT, m.ROWS_TABLE_KEY_PRIOR):
        fa = by_key[tk].footer_anchor
        assert fa is not None and fa.carries_total_formula is True


# ═══════════════════════════════════════════════════════════════════════════
# 判据 3：store 投影身份 + fail-closed
# ═══════════════════════════════════════════════════════════════════════════
def _store(cur_rows, prior_rows, *, cur_ta=1000, cur_tq=50, pri_ta=800, pri_tq=40):
    return json.dumps({
        "current": {"rows": cur_rows, "totalAmount": cur_ta, "totalQuantity": cur_tq},
        "prior": {"rows": prior_rows, "totalAmount": pri_ta, "totalQuantity": pri_tq},
    })


def test_projection_splits_regions_by_table_key(contract) -> None:
    payload = _store(
        [{"rowId": "c1", "name": "客户A", "amount": 600, "quantity": 30, "priorRank": "1"}],
        [{"rowId": "p1", "name": "客户B", "amount": 500, "quantity": 25, "priorRank": "2"}],
    )
    combined = m.build_d49_store_projection(payload, contract=contract)
    keys = set(str(k) for k in combined.stable_keys())
    assert any(k.startswith(m.ROWS_TABLE_KEY_CURRENT + "/") for k in keys)
    assert any(k.startswith(m.ROWS_TABLE_KEY_PRIOR + "/") for k in keys)
    assert any(k.startswith(m.TOTALS_TABLE_KEY + "/") for k in keys)
    tot_key = m.stable_key_for_total("current_total_amount")
    assert combined.get(tot_key).row_key is None
    assert combined.get(tot_key).value == 1000


def test_missing_row_id_fails_closed(contract) -> None:
    payload = _store([{"name": "无身份", "amount": 1}], [])
    with pytest.raises(m.StorePayloadError):
        m.build_d49_store_projection(payload, contract=contract)


def test_duplicate_row_id_fails_closed(contract) -> None:
    payload = _store([{"rowId": "dup", "name": "A"}, {"rowId": "dup", "name": "B"}], [])
    with pytest.raises(m.StorePayloadError):
        m.build_d49_store_projection(payload, contract=contract)


def test_same_row_id_across_regions_is_allowed(contract) -> None:
    payload = _store([{"rowId": "x", "name": "本期"}], [{"rowId": "x", "name": "上期"}])
    combined = m.build_d49_store_projection(payload, contract=contract)
    assert combined.get(m.stable_key_for_current("customer_name", "x")).value == "本期"
    assert combined.get(m.stable_key_for_prior("customer_name", "x")).value == "上期"


def test_legacy_bare_list_payload_tolerated_not_crash_entry(contract) -> None:
    """真实项目（首汽租车等）存在旧形态 D4-9-data = bare list（早于 {current,prior} 模型）。

    合并到共享 entry 后，此形态**不得** fail-closed 打挂全 entry rematerialize，而应视为空
    legacy 载荷 → 投影为空（0 行）。totals(amount) 归一为 0，与 materialize 空金额单元格
    反读一致（防 RoundtripEquivalenceError）。2026-09-20 修复回归守卫。
    """
    import json

    legacy = json.dumps([{"客户": "旧数据", "金额": 100}])  # bare list，无 current/prior
    proj = m.build_d49_store_projection(legacy, contract=contract)
    # 无行投影（两区 rows 皆空）
    assert proj.row_keys.get(m.ROWS_TABLE_KEY_CURRENT, ()) == ()
    assert proj.row_keys.get(m.ROWS_TABLE_KEY_PRIOR, ()) == ()
    # totals amount 归一为 0（非 None），防 roundtrip 不等值
    tot = proj.get(m.stable_key_for_total("current_total_amount"))
    assert tot is not None and tot.value == 0


def test_dict_but_malformed_region_still_fails_closed(contract) -> None:
    """容差只放行「整体非 dict」的 legacy 数组；dict 但内部 rows 畸形仍严格 fail-closed。"""
    import json

    bad = json.dumps({"current": {"rows": [{"name": "无身份"}]}, "prior": {"rows": []}})
    with pytest.raises(m.StorePayloadError):
        m.build_d49_store_projection(bad, contract=contract)


# ═══════════════════════════════════════════════════════════════════════════
# 判据 4：投影→合并 roundtrip（离线，逐字段对齐，两区不串）
# ═══════════════════════════════════════════════════════════════════════════
def test_projection_merge_roundtrip(contract) -> None:
    cur_rows = [
        {"rowId": "c1", "name": "客户A", "amount": 600, "quantity": 30, "priorRank": "2"},
        {"rowId": "c2", "name": "客户B", "amount": 400, "quantity": 20, "priorRank": "1"},
    ]
    prior_rows = [{"rowId": "p1", "name": "客户C", "amount": 500, "quantity": 25, "priorRank": "1"}]
    payload = _store(cur_rows, prior_rows, cur_ta=1000, cur_tq=50, pri_ta=500, pri_tq=25)
    combined = m.build_d49_store_projection(payload, contract=contract)
    merged, applied, visited, touched = m.merge_projection_into_d49_store(
        projection=combined, base_state=json.loads(payload),
    )
    assert [r["name"] for r in merged["current"]["rows"]] == ["客户A", "客户B"]
    assert [r["amount"] for r in merged["current"]["rows"]] == [600, 400]
    assert [r["name"] for r in merged["prior"]["rows"]] == ["客户C"]
    assert len(merged["prior"]["rows"]) == 1
    assert merged["current"]["totalAmount"] == 1000
    assert merged["current"]["totalQuantity"] == 50
    assert merged["prior"]["totalAmount"] == 500
    assert merged["prior"]["totalQuantity"] == 25


def test_parent_contract_disk_source_locked() -> None:
    """父契约（含 D4-9 sibling sheet）磁盘 ↔ 现算 payload 双向锁死。"""
    parent.assert_contract_file_matches_source()
