# -*- coding: utf-8 -*-
"""g7 / h1 缺失的 merge 门面修复判据 + b60 形态归类判据。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 13 的缺陷修复 · Requirements 3.1 / 3.4

═══ 修的是什么（2026-09-26 实测的既存缺陷）═══

`oo_to_html` 的回写分派对三家写了 `bridge.STORE_ITEM_ID` /
`bridge.merge_projection_into_store_rows` / `…_store_state`，而实测：

| provider | `STORE_ITEM_ID` | merge 函数 | 真实性质 |
|---|---|---|---|
| `pilot_simple_checklist`（b60） | **无** | **无** | 🔴 **不是缺陷**：契约无 `html_store` 段、15 字段 `store_item_id` 全 None ⇒ 纯 Excel entry |
| `pilot_g7_two_level_dynamic` | 有 | **缺** `…_store_state` | 🔴 真缺陷 ⇒ 本轮补齐 |
| `pilot_h1_grouped_dynamic` | 有 | **缺** `…_store_rows` | 🔴 真缺陷 ⇒ 本轮补齐 |

⇒ g7/h1 走到 store 镜像那步就是 `AttributeError` → opaque 500（「OO 保存后结构化视图
永远看不到回写」）。缺陷能长期活着是因为两家 adapter 也未注册、那条路径没人真走到过。

本文件既证明修复有效（merge 真的把值合进 store），也证明 b60 的归类正确（不是缺陷）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import pilot_g7_two_level_dynamic as G7
from app.services.workpaper_sync import pilot_h1_grouped_dynamic as H1
from app.services.workpaper_sync.contracts import parse_contract


class _FV:
    """最小 FieldValue 替身（只需 value / row_key / is_protected 三个读点）。"""

    def __init__(self, stable_key: str, value, row_key=None, is_protected: bool = False):
        self.stable_key = stable_key
        self.value = value
        self.row_key = row_key
        self.is_protected = is_protected


class _Proj:
    def __init__(self, values: dict[str, _FV]):
        self._values = values

    def stable_keys(self):
        return tuple(self._values)

    def get(self, key):
        return self._values.get(key)


# ═══════════════════════════════════════════════════════════════════════════
# h1：rows 形态 merge 门面
# ═══════════════════════════════════════════════════════════════════════════


def test_h1_merge_gateway_now_exists() -> None:
    """缺陷修复的最直接断言：符号存在且可调用（此前 AttributeError → opaque 500）。"""
    assert callable(getattr(H1, "merge_projection_into_store_rows", None))
    assert "merge_projection_into_store_rows" in H1.__all__


def test_h1_merge_applies_values_into_existing_row() -> None:
    """把 projection 的值合进已存在的行；applied/visited/touched 如实计数。"""
    rid = "disp-abc-0001"
    # 取两个真实字段：asset_name(D) 与 category(B)
    name_key = H1.stable_key_for("asset_name", rid)
    cat_key = H1.stable_key_for("category", rid)
    proj = _Proj({
        name_key: _FV(name_key, "打印机", row_key=rid),
        cat_key: _FV(cat_key, "电子设备", row_key=rid),
    })
    base = [{H1.ROW_IDENTITY_STORE_KEY: rid, "name": "旧名", "category": "旧类"}]

    rows, applied, visited, touched = H1.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert len(rows) == 1
    assert rows[0]["name"] == "打印机"      # json_path 为 `name`（不是 asset_name）
    assert rows[0]["category"] == "电子设备"
    assert applied == 2
    assert visited == 2
    assert touched == {rid}


def test_h1_merge_is_idempotent_when_values_unchanged() -> None:
    """值相同 ⇒ applied=0（`oo_to_html` 据此跳过写库，避免无意义大 JSON 刷新）。"""
    rid = "disp-abc-0002"
    name_key = H1.stable_key_for("asset_name", rid)
    proj = _Proj({name_key: _FV(name_key, "同值", row_key=rid)})
    base = [{H1.ROW_IDENTITY_STORE_KEY: rid, "name": "同值"}]
    _rows, applied, visited, touched = H1.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert applied == 0
    assert visited == 1
    assert touched == set()


def test_h1_merge_skips_protected_cells() -> None:
    """`is_protected`（公式格）不得被回写覆盖。"""
    rid = "disp-abc-0003"
    name_key = H1.stable_key_for("asset_name", rid)
    proj = _Proj({name_key: _FV(name_key, "不该写入", row_key=rid, is_protected=True)})
    base = [{H1.ROW_IDENTITY_STORE_KEY: rid, "name": "原值"}]
    rows, applied, _visited, _touched = H1.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert rows[0]["name"] == "原值"
    assert applied == 0


def test_h1_merge_ghost_row_guard_uses_business_name_not_seq() -> None:
    """🔴 幽灵行防护：新 identity 只有杂散字段（如 seq）而业务名称空 ⇒ 该行被丢弃。

    判据点在「用 asset_name 而非首列 seq」：`seq` 是 `auto_source` 序号，
    若用它作判据，「只填了序号的空行」会被当成真行留下（结构化视图里出现
    「有 rowId、没数据」的幽灵行 —— D4-2 同源缺陷）。
    """
    ghost = "disp-ghost-0001"
    seq_key = H1.stable_key_for("seq", ghost)
    proj = _Proj({seq_key: _FV(seq_key, 7, row_key=ghost)})
    rows, _applied, _visited, touched = H1.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert rows == [], "只有 seq 非空的新行应被判为幽灵行并丢弃"
    assert ghost not in touched


def test_h1_merge_keeps_pre_existing_row_even_if_name_cleared() -> None:
    """已存在的行清空名称是**合法编辑**，不得被幽灵行门删掉。"""
    rid = "disp-exists-0001"
    name_key = H1.stable_key_for("asset_name", rid)
    proj = _Proj({name_key: _FV(name_key, "", row_key=rid)})
    base = [{H1.ROW_IDENTITY_STORE_KEY: rid, "name": "原名"}]
    rows, applied, _visited, _touched = H1.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert len(rows) == 1, "已存在的行被清空名称后不得删除（清空是合法编辑）"
    assert rows[0]["name"] == ""
    assert applied == 1


def test_h1_merge_creates_row_when_name_is_present() -> None:
    """新 identity 若带业务名称 ⇒ 正常创建（不是幽灵行）。"""
    rid = "disp-new-0001"
    name_key = H1.stable_key_for("asset_name", rid)
    proj = _Proj({name_key: _FV(name_key, "新增资产", row_key=rid)})
    rows, applied, _visited, touched = H1.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert len(rows) == 1
    assert rows[0][H1.ROW_IDENTITY_STORE_KEY] == rid
    assert rows[0]["name"] == "新增资产"
    assert applied == 1
    assert touched == {rid}


def test_h1_merge_roundtrips_with_real_projection() -> None:
    """真链：用真契约 + 真 build_store_projection 产出的 projection 往返合并，值等价。"""
    contract = parse_contract(H1.build_contract_payload(), adapter_id=H1.PILOT_ADAPTER_ID)
    rid = "disp-rt-0001"
    row: dict = {H1.ROW_IDENTITY_STORE_KEY: rid}
    for spec in H1.MANAGED_FIELD_SPECS:
        json_path, value_type = spec[4], spec[3]
        row[json_path] = 123 if value_type in {"amount", "integer"} else "v"
    proj = H1.build_store_projection([row], contract=contract)

    merged, applied, visited, _touched = H1.merge_projection_into_store_rows(
        projection=proj, base_rows=[{H1.ROW_IDENTITY_STORE_KEY: rid}]
    )
    assert len(merged) == 1

    # 🔴 visited 只数**可写**字段：实测 25 个字段 = 22 editable + 2 formula + 1 auto_source，
    #    后三个由 `is_protected` 正确挡住（公式格与自动序号不得被 OO 回写覆盖）。
    #    本断言从 field_specs 现算而非手抄数字，字段增减时自动跟随。
    writable = [s for s in H1.MANAGED_FIELD_SPECS if s[2] == "editable"]
    protected = [s for s in H1.MANAGED_FIELD_SPECS if s[2] != "editable"]
    assert protected, "本表应含 formula/auto_source 列（否则 protected 分支未被覆盖）"
    assert visited == len(writable), (
        f"visited 应等于 editable 字段数 {len(writable)}，实得 {visited}；"
        f"被挡住的应是 {[s[0] for s in protected]}"
    )

    # 可写字段逐个等值
    for spec in writable:
        assert merged[0][spec[4]] == row[spec[4]], f"字段 {spec[0]} 往返不等值"
    # 🔴 受保护字段**保持 base 里的原样**（这里 base 没给 ⇒ 应压根不存在该键）
    for spec in protected:
        assert spec[4] not in merged[0], (
            f"受保护字段 {spec[0]}（mode={spec[2]}）不应被 OO 回写写入 store"
        )
    assert applied == len(writable)


# ═══════════════════════════════════════════════════════════════════════════
# g7：state 形态 merge 门面
# ═══════════════════════════════════════════════════════════════════════════


def test_g7_merge_gateway_now_exists() -> None:
    assert callable(getattr(G7, "merge_projection_into_store_state", None))


def _g7_base_state(entity_names: tuple[str, ...], metric_key: str) -> dict:
    return {
        "version": G7.STORE_STATE_VERSION,
        "tables": {G7.RENDER_MATRIX_TABLE_ID: [{"id": metric_key, "values": {}}]},
        "entitySlots": {G7.RENDER_SLOT: list(entity_names)},
        "texts": {"note": "保留我"},
    }


def _g7_first_metric_key() -> str:
    """从契约的 stable field key 反解一个真实 metric key。"""
    payload = G7.build_contract_payload()
    for sheet in payload["sheets"]:
        for table in sheet["tables"]:
            for field in table["fields"]:
                key = str(field["stable_field_key"])
                prefix = f"{G7.MATRIX_TABLE_KEY}/"
                if key.startswith(prefix):
                    metric, _, _col = key[len(prefix):].partition("/")
                    if metric:
                        return metric
    raise AssertionError("契约里找不到矩阵格字段")


def test_g7_merge_applies_matrix_cell() -> None:
    """把矩阵格的值合进 state；version / entitySlots / 其他段保留。"""
    metric = _g7_first_metric_key()
    entities = ("甲公司", "乙公司")
    column_keys = G7.dynamic_column_keys_for_entities(entities)
    assert column_keys, "实体清单应能派生动态列键"
    target_col = column_keys[0]
    render_key = G7.render_column_key_for_seq(1)

    stable_key = G7.stable_key_for_metric_cell(metric, target_col)
    proj = _Proj({stable_key: _FV(stable_key, 8888)})

    state, applied, visited = G7.merge_projection_into_store_state(
        projection=proj, base_state=_g7_base_state(entities, metric)
    )
    assert applied == 1
    assert visited == 1
    rows = state["tables"][G7.RENDER_MATRIX_TABLE_ID]
    assert rows[0]["values"][render_key] == 8888
    # 保留不属本表的段
    assert state["version"] == G7.STORE_STATE_VERSION
    assert state["entitySlots"][G7.RENDER_SLOT] == list(entities)
    assert state["texts"] == {"note": "保留我"}


def test_g7_merge_does_not_invent_metric_rows() -> None:
    """🔴 fail-closed：契约外/ state 里不存在的 metric **不新建行**（不得凭空造结构）。"""
    metric = _g7_first_metric_key()
    entities = ("甲公司",)
    col = G7.dynamic_column_keys_for_entities(entities)[0]
    bogus_key = G7.stable_key_for_metric_cell("metric-does-not-exist", col)
    proj = _Proj({bogus_key: _FV(bogus_key, 1)})

    state, applied, visited = G7.merge_projection_into_store_state(
        projection=proj, base_state=_g7_base_state(entities, metric)
    )
    assert applied == 0
    assert visited == 0
    rows = state["tables"][G7.RENDER_MATRIX_TABLE_ID]
    assert len(rows) == 1, "不得为不存在的 metric 新建行"
    assert rows[0]["id"] == metric


def test_g7_merge_does_not_invent_entity_columns() -> None:
    """🔴 fail-closed：实体清单外的列**不写入**（entitySlots 是实体真源，OO 改不了公司清单）。"""
    metric = _g7_first_metric_key()
    entities = ("甲公司",)   # 只有 1 家 ⇒ 只有 1 个合法列键
    all_cols = G7.dynamic_column_keys_for_entities(("甲公司", "乙公司", "丙公司"))
    out_of_range = all_cols[-1]   # 第 3 家的列键，不在当前 entitySlots 内
    key = G7.stable_key_for_metric_cell(metric, out_of_range)
    proj = _Proj({key: _FV(key, 999)})

    state, applied, visited = G7.merge_projection_into_store_state(
        projection=proj, base_state=_g7_base_state(entities, metric)
    )
    assert applied == 0
    assert visited == 0
    assert state["tables"][G7.RENDER_MATRIX_TABLE_ID][0]["values"] == {}


def test_g7_merge_idempotent_and_protected_skip() -> None:
    metric = _g7_first_metric_key()
    entities = ("甲公司",)
    col = G7.dynamic_column_keys_for_entities(entities)[0]
    render_key = G7.render_column_key_for_seq(1)
    key = G7.stable_key_for_metric_cell(metric, col)

    base = _g7_base_state(entities, metric)
    base["tables"][G7.RENDER_MATRIX_TABLE_ID][0]["values"] = {render_key: 42}

    # 同值 ⇒ applied=0
    _state, applied, visited = G7.merge_projection_into_store_state(
        projection=_Proj({key: _FV(key, 42)}), base_state=base
    )
    assert (applied, visited) == (0, 1)

    # protected ⇒ 不写
    state2, applied2, _v2 = G7.merge_projection_into_store_state(
        projection=_Proj({key: _FV(key, 777, is_protected=True)}), base_state=base
    )
    assert applied2 == 0
    assert state2["tables"][G7.RENDER_MATRIX_TABLE_ID][0]["values"][render_key] == 42


def test_g7_merge_handles_none_base_state() -> None:
    """base_state 为 None（store 里还没有这条 item）⇒ 不崩，产出带 version 的空骨架。"""
    state, applied, visited = G7.merge_projection_into_store_state(
        projection=_Proj({}), base_state=None
    )
    assert state["version"] == G7.STORE_STATE_VERSION
    assert (applied, visited) == (0, 0)


# ═══════════════════════════════════════════════════════════════════════════
# b60：不是缺陷，是形态不同
# ═══════════════════════════════════════════════════════════════════════════


def test_b60_has_no_html_store_by_design() -> None:
    """🔴 b60 的契约**无 `html_store` 段**、字段 `store_item_id` 全 None ⇒ 纯 Excel entry。

    本判据钉住「它不是缺 merge 门面，而是压根不需要 store 镜像」这条事实，
    修正了首版把三家一概标成「缺门面」的误判。
    """
    path = (
        _BACKEND / "data" / "workpaper_sync_contracts" / "b60.hour_budget.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "html_store" not in payload.get("review", {}), (
        "b60 契约若有 html_store 段，说明它确实需要镜像 ⇒ 本判据与归类都须重写"
    )
    item_ids = {
        f.get("store_item_id")
        for sheet in payload["sheets"]
        for table in sheet["tables"]
        for f in table["fields"]
    }
    assert item_ids == {None}, f"b60 字段的 store_item_id 应全为 None，实得 {item_ids}"


def test_b60_is_registered_as_non_store_backed() -> None:
    """b60 走 `NON_STORE_BACKED_ADAPTERS` 直接跳过，不经 resolve（不抛错、不镜像）。"""
    from app.services.workpaper_sync.store_item_registry import (
        NON_STORE_BACKED_ADAPTERS,
        store_merge_plan_or_skip,
    )

    assert "b60.hour_budget" in NON_STORE_BACKED_ADAPTERS
    assert store_merge_plan_or_skip("b60.hour_budget") is None


def test_g7_and_h1_now_resolve_without_error() -> None:
    """修复后 g7/h1 必须能正常 resolve（此前被 mirror_unavailable_reason 挡住）。"""
    from app.services.workpaper_sync.store_item_registry import store_merge_plan_or_skip

    for adapter_id, fn_attr in (
        ("g7.soe_subsidiary_disclosure", "merge_state_fn"),
        ("h1.disposal_check", "merge_rows_fn"),
    ):
        plan = store_merge_plan_or_skip(adapter_id)
        assert plan is not None, f"{adapter_id} 应能解析出 plan"
        assert not plan.mirror_unavailable_reason, (
            f"{adapter_id} 的门面已补齐，mirror_unavailable_reason 应清空"
        )
        # 注册表声明的函数名必须在 provider 上真实存在（防「注册表写了名、provider 没这符号」）
        import importlib

        bridge = importlib.import_module(
            f"app.services.workpaper_sync.{plan.provider_module}"
        )
        fn_name = getattr(plan, fn_attr)
        assert fn_name and hasattr(bridge, fn_name), (
            f"{plan.provider_module} 缺 {fn_name}"
        )
        assert hasattr(bridge, "STORE_ITEM_ID")
