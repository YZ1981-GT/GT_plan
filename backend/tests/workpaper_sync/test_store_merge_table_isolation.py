# -*- coding: utf-8 -*-
"""回写合并只合本表的键 + F2 dict store 的 state 合并（spec oo-writeback-template-parity-closure R3）。

═══ 锁的是什么缺陷（2026-10-27 普查实证）═══

单 item 回写路径（`store_mirror` 单 item 分支）把**整份契约**的 merged projection 交给 provider 的
merge 门面，框架引擎 `merge_projection_into_store_rows` 原先只按 column_key 过滤键。别的行表列名
常与本表重名 ⇒ 别表在 OO 里新增的行被建进本 item 的 store：d3（凭证抽查两区进 D3-det-rows）/
d5（D5-4 进 D5-2）/ e1（数字货币进现金）/ f2 valuation（F2-47 进 F2-48）/ f2 stocktake（区二进区一）/
f3（六张表进 F3-5）/ h3 / h7（公允价值进成本）。多区共用一个 store item 的门面（G9 / L5）逐段穿线时，
区②/③ 的新增行在区① 那一趟就被建出、带上区① 的归属 —— 回到 HTML 落错区。

F2-48 / F2-57 的 store 是 dict（`{products}` / `{projects}`），原先走 rows 分支：基线恒为 `[]`、
写回裸数组 ⇒ 外层键与非受管字段丢失，前端读到裸数组按旧版形态迁移、行身份重新生成。

═══ 判据 ═══

1. 逐个已注册的单 item 行表 adapter，用契约真表造一行投影：别的 store item 的表造的行不进本 item；
   本 item 的表造的行进 store，多区时带本区的区归属（已知缺口逐条登记，修好即删）。
2. 引擎层：F2-47 表的键喂给 F2-48 的 spec 不建行。
3. F2 dict store：state 合并只换行数组，外层键与行内非受管字段保留；出方向按名取行数组。
"""
from __future__ import annotations

import importlib
import json
from typing import Any

import pytest

from app.services.workpaper_sync.adapters.base import FieldValue, Projection
from app.services.workpaper_sync.contracts import FieldMode, ValueType, load_contract
from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY, StoreKind

PROBE = "probe-table-isolation-1"

#: 本 item 自己的表造的行**不该**长出来的（不是缺陷）
OWN_TABLE_NOT_CREATING: dict[tuple[str, str], str] = {
    ("i5.other_noncurrent_assets_detail", "other_noncurrent_impairment_rows"): (
        "减值区与原值区共用一行（同一 rowId），行名称在原值区；只在减值区新增的行没有名称 ⇒ 幽灵行门剔除"
    ),
}

#: 已知缺口（批 B 修；修好后本条失效即报红，必须删）
KNOWN_GAPS: dict[tuple[str, str], str] = {
    ("g1.trading_financial_assets_detail", "g1_2_rows_r2"): "G1 门面只取区① 的 spec，区②/③ 两个方向都没接",
    ("g1.trading_financial_assets_detail", "g1_2_rows_r3"): "同上",
    ("g3.dividend_receivable_detail", "g3_2_rows_r1"): "G3 重导出的 store 门面绑死在 G9 的 spec 上",
    ("g3.dividend_receivable_detail", "g3_2_rows_r2"): "同上",
}


def _probe_value(value_type: str) -> Any:
    if value_type == "text":
        return "探针文本"
    if value_type == "date":
        return "2025-12-31"
    if value_type == "boolean":
        return True
    return 7


def _projection(contract: Any, table: dict, *, rid: str = PROBE, values: dict | None = None) -> Projection:
    """契约真表的一行投影；`values` 缺省 = 每个列都给探针值。"""
    tk = table["table_key"]
    out: dict[str, FieldValue] = {}
    for f in table["fields"]:
        ck = f.get("column_key")
        if not ck:
            continue
        if values is not None and ck not in values:
            continue
        sk = f"{tk}/{rid}/{ck}"
        out[sk] = FieldValue(
            stable_key=sk,
            value=_probe_value(f["value_type"]) if values is None else values[ck],
            value_type=ValueType(f["value_type"]),
            mode=FieldMode("editable"),
            row_key=rid,
        )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=out,
        row_keys={tk: (rid,)},
    )


def _dynamic_tables(contract: Any) -> list[dict]:
    return [
        t
        for s in contract.canonical_payload.get("sheets", [])
        for t in s.get("tables", [])
        if t.get("row_identity")
    ]


def _table_store_items(table: dict) -> set[str]:
    return {str(f.get("store_item_id")) for f in table["fields"]}


def _json_paths(table: dict) -> set[str]:
    return {
        str(f["json_pointer"]).split("{row_uuid}/", 1)[-1]
        for f in table["fields"]
        if "{row_uuid}/" in str(f.get("json_pointer") or "")
    }


def _single_path_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for aid, plan in sorted(STORE_MERGE_REGISTRY.items()):
        if plan.dual_store_fn or plan.merge_state_fn or not plan.items:
            continue
        if any(item.kind is not StoreKind.rows for item in plan.items):
            continue
        tables = _dynamic_tables(load_contract(aid))
        if len(tables) <= 1:
            continue
        cases.extend((aid, t["table_key"]) for t in tables)
    return cases


_CASES = _single_path_cases()


def test_case_universe_is_not_vacuous() -> None:
    adapters = {a for a, _ in _CASES}
    # 普查时 16 家；判据范围骤降说明注册表 / 契约形态变了，先复读再改阈值
    assert len(adapters) >= 14, sorted(adapters)
    assert {"f2.stocktake_bundle", "e1.monetary_fund_detail", "g9.other_noncurrent_detail"} <= adapters


@pytest.mark.parametrize("adapter_id,table_key", _CASES)
def test_probe_row_lands_only_in_its_own_store_item(adapter_id: str, table_key: str) -> None:
    plan = STORE_MERGE_REGISTRY[adapter_id]
    bridge = importlib.import_module(f"app.services.workpaper_sync.{plan.provider_module}")
    contract = load_contract(adapter_id)
    table = next(t for t in _dynamic_tables(contract) if t["table_key"] == table_key)
    merge = getattr(bridge, plan.merge_rows_fn)
    rows, _applied, _visited, _touched = merge(projection=_projection(contract, table), base_rows=[])
    grown = [r for r in rows if PROBE in json.dumps(r, ensure_ascii=False)]
    own = _table_store_items(table) == {str(bridge.STORE_ITEM_ID)}
    key = (adapter_id, table_key)

    if not own:
        assert grown == [], f"{table_key} 的行被建进了 {bridge.STORE_ITEM_ID}（串表）：{grown}"
        return
    if key in OWN_TABLE_NOT_CREATING:
        assert grown == [], OWN_TABLE_NOT_CREATING[key]
        return
    if key in KNOWN_GAPS:
        assert grown == [], f"已知缺口已修好（{KNOWN_GAPS[key]}）—— 删掉 KNOWN_GAPS 这一条"
        return
    assert len(grown) == 1, f"{table_key} 自己的行没进 {bridge.STORE_ITEM_ID}"
    # D3 / D5 / D6 / D7 的 entry 模块没有 spec 清单（扩容面在伴生模块），它们本身是单区
    specs_fn = getattr(bridge, "managed_row_table_specs", None)
    specs = {s.table_key: s for s in specs_fn()} if callable(specs_fn) else {}
    spec = specs.get(table_key)
    if spec is not None and spec.row_section_field and spec.row_section_field not in _json_paths(table):
        assert grown[0].get(spec.row_section_field) == spec.row_section_value, (
            f"{table_key} 新增行落错区：{grown[0].get(spec.row_section_field)!r}，应为 {spec.row_section_value!r}"
        )


def test_known_gap_entries_are_still_in_the_case_universe() -> None:
    stale = [k for k in (*KNOWN_GAPS, *OWN_TABLE_NOT_CREATING) if k not in _CASES]
    assert stale == []


# ═══════════════════════════════════════════════════════════════════════════
# 引擎层
# ═══════════════════════════════════════════════════════════════════════════


def test_engine_ignores_keys_of_other_tables() -> None:
    from app.services.workpaper_sync.phase5_f2_valuation_47_48_49 import SPEC_F247, SPEC_F248
    from app.services.workpaper_sync.phase5_row_table_sheet import merge_projection_into_store_rows

    contract = load_contract("f2.inventory_valuation")
    tables = {t["table_key"]: t for t in _dynamic_tables(contract)}
    foreign = _projection(contract, tables[SPEC_F247.table_key])
    own = _projection(contract, tables[SPEC_F248.table_key])
    # 前提：两表确有重名列（否则判据不成立）
    cols = lambda t: {f["column_key"] for f in t["fields"]}  # noqa: E731
    assert {"category", "item_code", "item_name", "qty"} <= cols(tables[SPEC_F247.table_key]) & cols(
        tables[SPEC_F248.table_key]
    )
    rows, applied, _v, _t = merge_projection_into_store_rows(SPEC_F248, projection=foreign, base_rows=[])
    assert (rows, applied) == ([], 0)
    rows, applied, _v, _t = merge_projection_into_store_rows(SPEC_F248, projection=own, base_rows=[])
    assert [r["id"] for r in rows] == [PROBE] and applied > 0


# ═══════════════════════════════════════════════════════════════════════════
# F2 dict store 的 state 合并 / 出方向按名取行数组
# ═══════════════════════════════════════════════════════════════════════════

_DICT_CASES = (
    # adapter, provider, store item, 行数组键, 改的列, 新值, 非受管字段
    ("f2.inventory_valuation", "phase5_f2_inventory_valuation", "F2-48-rows", "products", "qty", 9, "rowNote"),
    ("f2.inventory_special", "phase5_f2_inventory_special", "F2-57-rows", "projects", "book_balance", 9, "remark"),
)


@pytest.mark.parametrize("adapter_id,provider,item,rows_key,column,value,unmanaged", _DICT_CASES)
def test_f2_dict_store_state_merge_keeps_wrapper_and_unmanaged_fields(
    adapter_id: str, provider: str, item: str, rows_key: str, column: str, value: Any, unmanaged: str
) -> None:
    plan = STORE_MERGE_REGISTRY[adapter_id]
    assert plan.merge_state_fn == "merge_projection_into_store_state", "dict store 必须走 state 分支"
    mod = importlib.import_module(f"app.services.workpaper_sync.{provider}")
    assert mod.STORE_ITEM_ID == item
    contract = load_contract(adapter_id)
    spec = next(s for s in mod.managed_row_table_specs() if s.store_item_id == item)
    table = next(t for t in _dynamic_tables(contract) if t["table_key"] == spec.table_key)
    json_key = next(f for f in spec.field_specs if f[0] == column)[4]
    base = {
        rows_key: [{"id": "row-a", json_key: 1, unmanaged: "前端独有"}],
        "外层键": {"保留": True},
    }
    state, applied, _visited = getattr(mod, plan.merge_state_fn)(
        projection=_projection(contract, table, rid="row-a", values={column: value}),
        base_state=json.loads(json.dumps(base)),
    )
    assert applied == 1
    assert state["外层键"] == {"保留": True}
    assert state[rows_key] == [{"id": "row-a", json_key: value, unmanaged: "前端独有"}]


@pytest.mark.parametrize("adapter_id,provider,item,rows_key,column,value,unmanaged", _DICT_CASES)
def test_f2_dict_store_projection_reads_the_named_rows_array(
    adapter_id: str, provider: str, item: str, rows_key: str, column: str, value: Any, unmanaged: str
) -> None:
    mod = importlib.import_module(f"app.services.workpaper_sync.{provider}")
    contract = load_contract(adapter_id)
    spec = next(s for s in mod.managed_row_table_specs() if s.store_item_id == item)
    json_key = next(f for f in spec.field_specs if f[0] == column)[4]
    # 行数组之前放一个别的数组：按「第一个列表值」取会取错
    payload = {"aaa先到的数组": [{"id": "decoy", json_key: 5}], rows_key: [{"id": "row-a", json_key: value}]}
    proj = mod.build_store_projection(json.dumps(payload, ensure_ascii=False), contract=contract, store_item_id=item)
    rows = {fv.row_key for fv in proj.values.values()}
    assert rows == {"row-a"}
    assert proj.values[f"{spec.table_key}/row-a/{column}"].value == value
