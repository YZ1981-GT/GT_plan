# -*- coding: utf-8 -*-
"""D4-1 营业收入审定表 store projection provider 契约测试。

spec: d4-1-adjudication-bidirectional-writeback-and-formula-io · Task 2.1（后端 provider）

覆盖：
- 磁盘契约 == 现算 payload（assert_contract_file_matches_source，含真跑 parse_contract）；
- store JSON → projection → merge_projection_into_store 往返，rowId/label/六字段/tbCheck 逐字段一致；
- 缺 rowId / 重复 rowId → StorePayloadError（fail-closed）；
- formula_mask 的 E/I 审定列不出现在可回写 projection 值里（protected）；
- 两段行不串（main 的 rowId 不进 other table_key）；
- 反向自检：合法 store → projection 非空、stable_key 前缀正确（判据不恒真）。
"""
from __future__ import annotations

import json

import pytest

from app.services.workpaper_sync import phase5_d4_operating_revenue as m


def _sample_store() -> dict:
    """一份合法 D4-1 store 载荷（两段各 2 行 + tbCheck）。"""
    return {
        "main": {
            "rows": [
                {
                    "rowId": "gtrow-main-0001",
                    "label": "商品销售收入",
                    "currentUnadjusted": 1000.0,
                    "currentAje": 10.0,
                    "currentRje": 0.0,
                    "currentAudited": 1010.0,  # 派生列（不应回写）
                    "priorUnadjusted": 900.0,
                    "priorAje": 0.0,
                    "priorRje": 5.0,
                    "priorAudited": 905.0,
                },
                {
                    "rowId": "gtrow-main-0002",
                    "label": "劳务收入",
                    "currentUnadjusted": 500.0,
                    "currentAje": 0.0,
                    "currentRje": 0.0,
                    "priorUnadjusted": 480.0,
                    "priorAje": 0.0,
                    "priorRje": 0.0,
                },
            ]
        },
        "other": {
            "rows": [
                {
                    "rowId": "gtrow-other-0001",
                    "label": "租金收入",
                    "currentUnadjusted": 200.0,
                    "currentAje": 0.0,
                    "currentRje": 0.0,
                    "priorUnadjusted": 190.0,
                    "priorAje": 0.0,
                    "priorRje": 0.0,
                }
            ]
        },
        "tbCheck": {"tb6001": 1515.0, "tb6051": 200.0},
    }


@pytest.fixture()
def contract():
    return m.load_contract_from_disk()


# ── 1. 磁盘契约 == 现算 payload ──────────────────────────────────────
def test_contract_file_matches_source():
    c = m.assert_contract_file_matches_source()
    assert c.contract_id == m.ADAPTER_ID
    assert c.document_type == "xlsx"


def test_contract_has_three_tables(contract):
    sheet = contract.sheets[0]
    table_keys = {t.table_key for t in sheet.tables}
    assert table_keys == {m.MAIN_TABLE_KEY, m.OTHER_TABLE_KEY, m.TB_CHECK_TABLE_KEY}


# ── 2. 往返：store → projection → merge → store ─────────────────────
def test_roundtrip_fidelity(contract):
    store = _sample_store()
    projection = m.build_operating_revenue_store_projection(store, contract=contract)
    projection.assert_matches_contract(contract)

    merged, applied = m.merge_projection_into_store(projection=projection, base_payload=None)
    assert applied > 0

    # 两段行数一致。
    assert len(merged["main"]["rows"]) == 2
    assert len(merged["other"]["rows"]) == 1

    # 逐字段（rowId/label/六输入字段）一致 —— 审定列由公式派生不校验。
    def _index(rows):
        return {r["rowId"]: r for r in rows}

    src_main = _index(store["main"]["rows"])
    got_main = _index(merged["main"]["rows"])
    assert set(src_main) == set(got_main)
    input_keys = [
        "currentUnadjusted", "currentAje", "currentRje",
        "priorUnadjusted", "priorAje", "priorRje",
    ]
    for rid, src in src_main.items():
        got = got_main[rid]
        assert got["label"] == src["label"]
        for k in input_keys:
            assert got.get(k) == src.get(k), (rid, k)

    src_other = _index(store["other"]["rows"])
    got_other = _index(merged["other"]["rows"])
    for rid, src in src_other.items():
        assert got_other[rid]["label"] == src["label"]
        for k in input_keys:
            assert got_other[rid].get(k) == src.get(k)

    # tbCheck 标量一致。
    assert merged["tbCheck"]["tb6001"] == store["tbCheck"]["tb6001"]
    assert merged["tbCheck"]["tb6051"] == store["tbCheck"]["tb6051"]


def test_roundtrip_accepts_json_string(contract):
    store = _sample_store()
    projection = m.build_operating_revenue_store_projection(
        json.dumps(store, ensure_ascii=False), contract=contract
    )
    merged, _ = m.merge_projection_into_store(projection=projection, base_payload=None)
    assert {r["rowId"] for r in merged["main"]["rows"]} == {
        "gtrow-main-0001", "gtrow-main-0002",
    }


# ── 3. fail-closed：缺 rowId / 重复 rowId ────────────────────────────
def test_missing_row_id_rejected(contract):
    store = _sample_store()
    del store["main"]["rows"][0]["rowId"]
    with pytest.raises(m.StorePayloadError, match="缺稳定行身份"):
        m.build_operating_revenue_store_projection(store, contract=contract)


def test_duplicate_row_id_rejected(contract):
    store = _sample_store()
    store["main"]["rows"][1]["rowId"] = store["main"]["rows"][0]["rowId"]
    with pytest.raises(m.StorePayloadError, match="重复行身份"):
        m.build_operating_revenue_store_projection(store, contract=contract)


def test_non_object_payload_rejected(contract):
    with pytest.raises(m.StorePayloadError):
        m.build_operating_revenue_store_projection("[1,2,3]", contract=contract)


def test_rows_not_list_rejected(contract):
    store = _sample_store()
    store["main"]["rows"] = {"not": "a list"}
    with pytest.raises(m.StorePayloadError, match="必须是数组"):
        m.build_operating_revenue_store_projection(store, contract=contract)


# ── 4. formula_mask 的 E/I 审定列 protected，不回写 ─────────────────
def test_audited_columns_are_protected(contract):
    store = _sample_store()
    projection = m.build_operating_revenue_store_projection(store, contract=contract)

    # 审定 stable key 在 projection 里存在但标记 protected。
    audited_key = m.stable_key_for_row(m.MAIN_TABLE_KEY, "current_audited", "gtrow-main-0001")
    fv = projection.get(audited_key)
    assert fv is not None and fv.is_protected

    # merge 回 store 时，派生列不落地（第一行原本 currentAudited=1010，被剔除后为空对象里不含它）。
    merged, _ = m.merge_projection_into_store(projection=projection, base_payload=None)
    row0 = next(r for r in merged["main"]["rows"] if r["rowId"] == "gtrow-main-0001")
    assert "currentAudited" not in row0
    assert "priorAudited" not in row0


def test_protected_field_keys_are_audited_only(contract):
    protected = set(contract.protected_field_keys())
    for table_key in (m.MAIN_TABLE_KEY, m.OTHER_TABLE_KEY):
        assert m.stable_key_for_row(table_key, "current_audited") in protected
        assert m.stable_key_for_row(table_key, "prior_audited") in protected
        # 输入列不得 protected。
        assert m.stable_key_for_row(table_key, "current_unadjusted") not in protected


# ── 5. 两段不串（main 的 rowId 不进 other table_key）────────────────
def test_sections_do_not_bleed(contract):
    store = _sample_store()
    projection = m.build_operating_revenue_store_projection(store, contract=contract)

    main_keys = [k for k in projection.stable_keys() if k.startswith(m.MAIN_TABLE_KEY + "/")]
    other_keys = [k for k in projection.stable_keys() if k.startswith(m.OTHER_TABLE_KEY + "/")]

    # main 的 rowId 只出现在 main_rows 前缀键里。
    assert any("gtrow-main-0001" in k for k in main_keys)
    assert not any("gtrow-main-0001" in k for k in other_keys)
    # other 的 rowId 只出现在 other_rows 前缀键里。
    assert any("gtrow-other-0001" in k for k in other_keys)
    assert not any("gtrow-other-0001" in k for k in main_keys)

    # row_keys 分段登记正确。
    assert projection.row_keys[m.MAIN_TABLE_KEY] == ("gtrow-main-0001", "gtrow-main-0002")
    assert projection.row_keys[m.OTHER_TABLE_KEY] == ("gtrow-other-0001",)


def test_merge_keeps_rows_in_own_section(contract):
    store = _sample_store()
    projection = m.build_operating_revenue_store_projection(store, contract=contract)
    merged, _ = m.merge_projection_into_store(projection=projection, base_payload=None)
    main_ids = {r["rowId"] for r in merged["main"]["rows"]}
    other_ids = {r["rowId"] for r in merged["other"]["rows"]}
    assert main_ids == {"gtrow-main-0001", "gtrow-main-0002"}
    assert other_ids == {"gtrow-other-0001"}
    assert main_ids.isdisjoint(other_ids)


# ── 6. 反向自检：判据不恒真 ─────────────────────────────────────────
def test_projection_non_empty_and_stable_key_prefix(contract):
    """构造合法 store：projection 必须非空、每个键前缀是三个已知 table_key 之一。

    这条防「投影恒空也能过前几条」的假绿 —— 若 provider 悄悄返回空 projection，
    往返断言可能因两侧都空而假过，这里直接断言非空 + 键结构。
    """
    store = _sample_store()
    projection = m.build_operating_revenue_store_projection(store, contract=contract)
    keys = projection.stable_keys()
    assert len(keys) > 0

    valid_prefixes = (m.MAIN_TABLE_KEY + "/", m.OTHER_TABLE_KEY + "/", m.TB_CHECK_TABLE_KEY + "/")
    for k in keys:
        assert k.startswith(valid_prefixes), k

    # 明确有三段的键各至少一个（否则某段被静默丢弃）。
    assert any(k.startswith(m.MAIN_TABLE_KEY + "/") for k in keys)
    assert any(k.startswith(m.OTHER_TABLE_KEY + "/") for k in keys)
    assert any(k.startswith(m.TB_CHECK_TABLE_KEY + "/") for k in keys)


def test_reverse_check_empty_store_yields_only_totals(contract):
    """空段 store（无 rows）：动态行投影为空，tbCheck 缺失时值为 None —— 断言不误判非空。"""
    store = {"main": {}, "other": {}, "tbCheck": {}}
    projection = m.build_operating_revenue_store_projection(store, contract=contract)
    keys = projection.stable_keys()
    # 只有 2 个 tb 标量键（值为 None）。
    assert set(keys) == {
        m.stable_key_for_total("tb_6001"),
        m.stable_key_for_total("tb_6051"),
    }
    assert projection.row_keys[m.MAIN_TABLE_KEY] == ()
    assert projection.row_keys[m.OTHER_TABLE_KEY] == ()
