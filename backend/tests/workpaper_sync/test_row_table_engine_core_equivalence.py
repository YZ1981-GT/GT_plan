# -*- coding: utf-8 -*-
"""行表引擎核心（投影/合并）与七家 provider 原实现的等价判据（Task 9）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 9 · Requirements 1.1 / 1.5 / 2.3

═══ 判据面 ═══

引擎的 `build_store_projection` / `merge_projection_into_store_rows` 必须与 provider 原实现
**逐字段等价**（同一 contract、同一 payload 驱动）。这是「阶段 3 逐家切换」的安全性来源：
切换前先证明引擎能复刻原行为，切换才只是改调用方。

覆盖三家代表：D1（无账龄，扁平 camelCase）/ D3（nested 账龄，含 `/` 路径）/ D6（flat 账龄）。
另覆盖两条 fail-closed 行为等价：非数组载荷、缺行身份、重复行身份。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d1_notes_receivable as D1
from app.services.workpaper_sync import phase5_d3_prepaid_receipts as D3
from app.services.workpaper_sync import phase5_d6_contract_assets as D6
from app.services.workpaper_sync import phase5_row_table_sheet as ENGINE
from app.services.workpaper_sync.contracts import parse_contract

from tests.workpaper_sync.test_row_table_engine_equivalence import (  # noqa: E402
    _spec_d1,
    _spec_d3,
    _spec_d6,
)


def _contract_of(provider):
    return parse_contract(
        provider.build_contract_payload(),
        adapter_id=getattr(provider, "ADAPTER_ID", None) or provider.PILOT_ADAPTER_ID,
    )


def _synthetic_rows(provider, *, count: int = 3) -> list[dict]:
    """按 provider 的 MANAGED_FIELD_SPECS 现造行（nested 路径逐级建 dict）。"""
    rows: list[dict] = []
    for i in range(count):
        row: dict = {provider.ROW_IDENTITY_STORE_KEY: f"syn-{i}"}
        for spec in provider.MANAGED_FIELD_SPECS:
            value_type, json_path = spec[3], spec[4]
            val = (i + 1) * 1000 if value_type in {"amount", "integer"} else f"t{i}"
            parts = str(json_path).split("/")
            cursor = row
            for seg in parts[:-1]:
                nxt = cursor.get(seg)
                if not isinstance(nxt, dict):
                    nxt = {}
                    cursor[seg] = nxt
                cursor = nxt
            cursor[parts[-1]] = val
        rows.append(row)
    return rows


def _projection_as_tuples(projection) -> list[tuple]:
    out = []
    for k in sorted(projection.stable_keys()):
        fv = projection.get(k)
        out.append((k, fv.value, fv.value_type, fv.mode, fv.row_key))
    return out


@pytest.mark.parametrize(
    "provider,spec_fn",
    [(D1, _spec_d1), (D3, _spec_d3), (D6, _spec_d6)],
    ids=["d1", "d3", "d6"],
)
def test_build_store_projection_equals_provider(provider, spec_fn) -> None:
    """引擎投影 ≡ provider 原投影（逐 (key,value,value_type,mode,row_key) 相等）。"""
    contract = _contract_of(provider)
    rows = _synthetic_rows(provider)

    original = provider.build_store_projection(rows, contract=contract)
    engine = ENGINE.build_store_projection(spec_fn(), rows, contract=contract)

    assert _projection_as_tuples(engine) == _projection_as_tuples(original)
    assert engine.row_keys == original.row_keys
    assert engine.contract_id == original.contract_id


@pytest.mark.parametrize(
    "provider,spec_fn",
    [(D1, _spec_d1), (D3, _spec_d3), (D6, _spec_d6)],
    ids=["d1", "d3", "d6"],
)
def test_merge_projection_into_store_rows_equals_provider(provider, spec_fn) -> None:
    """引擎合并 ≡ provider 原合并（行序、值、applied/visited/touched 全等）。"""
    contract = _contract_of(provider)
    rows = _synthetic_rows(provider)
    projection = provider.build_store_projection(rows, contract=contract)

    # base_rows 故意只给首行且清空一个值，制造真实 applied>0 的合并场景
    base = [dict(rows[0])]
    first_path = provider.MANAGED_FIELD_SPECS[1][4]
    parts = first_path.split("/")
    cursor = base[0]
    for seg in parts[:-1]:
        cursor = cursor.setdefault(seg, {})
    cursor[parts[-1]] = None

    orig_rows, orig_applied, orig_visited, orig_touched = provider.merge_projection_into_store_rows(
        projection=projection, base_rows=[dict(r) for r in base]
    )
    eng_rows, eng_applied, eng_visited, eng_touched = ENGINE.merge_projection_into_store_rows(
        spec_fn(), projection=projection, base_rows=[dict(r) for r in base]
    )

    assert eng_rows == orig_rows
    assert (eng_applied, eng_visited, eng_touched) == (orig_applied, orig_visited, orig_touched)


@pytest.mark.parametrize("provider,spec_fn", [(D1, _spec_d1), (D3, _spec_d3)], ids=["d1", "d3"])
def test_fail_closed_behaviours_match(provider, spec_fn) -> None:
    """三条 fail-closed 行为等价：非数组 / 缺行身份 / 重复行身份 —— 两侧都必须抛。"""
    spec = spec_fn()
    idk = provider.ROW_IDENTITY_STORE_KEY

    # 非数组
    with pytest.raises(provider.StorePayloadError):
        list(provider.iter_store_rows('{"a":1}'))
    with pytest.raises(ENGINE.RowTableStorePayloadError):
        list(ENGINE.iter_store_rows(spec, '{"a":1}'))

    # 缺行身份
    with pytest.raises(provider.StorePayloadError):
        list(provider.iter_store_rows([{"x": 1}]))
    with pytest.raises(ENGINE.RowTableStorePayloadError):
        list(ENGINE.iter_store_rows(spec, [{"x": 1}]))

    # 重复行身份
    dup = [{idk: "same"}, {idk: "same"}]
    with pytest.raises(provider.StorePayloadError):
        list(provider.iter_store_rows(dup))
    with pytest.raises(ENGINE.RowTableStorePayloadError):
        list(ENGINE.iter_store_rows(spec, dup))


def test_static_region_spec_rejects_row_projection() -> None:
    """row_identity_key='' （static_region 无行维度）⇒ 走行表投影必 fail closed。"""
    base = _spec_d1()
    static_spec = ENGINE.RowTableSheetSpec(
        **{
            **{f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()},
            "row_identity_key": "",
        }
    )
    with pytest.raises(ENGINE.RowTableStorePayloadError, match="static_region"):
        list(ENGINE.iter_store_rows(static_spec, [{"rowId": "x"}]))
