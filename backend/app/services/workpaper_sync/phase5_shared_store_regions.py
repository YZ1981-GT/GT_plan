"""一个 HTML store item 映射多张受管表（同一行同时落在多个物理区）的投影与合回。

spec: writeback-followup-issue-closure · R12（恢复未合入的实现）

I5-2 的原值区 / 减值区共用 store item `I5-2-rows`：HTML 一行同时有 `gross/*` 与 `impairment/*`
两组嵌套字段，Excel 上却是两张各带 UUID 列的表。H 骨架原来只取第一张 spec ⇒ 减值区在投影与
合回两个方向都被丢掉（`test_i_cycle_publish_and_multiregion` 自合入起即红）。

实现照未合入分支 `work/2026-10-01-i-cycle-classification-convergence` 的 02c7eb404
（`phase5_h_cycle_common` 的 `build_store_projection_for` / `merge_projection_into_store_rows_for`
多表分支）原样搬来，只拆成独立模块（骨架已到行数上限）：

* 投影：逐表跑行表引擎取并集；第二张起的行身份加可逆后缀 `~gt:{table_key}` ——
  同一个 HTML rowId 不能同时当两张 Excel 表的物理 identity（真 OO 实测：不分域时减值区
  45 个字段在 extract 后全部消失）。
* 合回：按 table 切片，依次合进同一组行，第二张起先去后缀；缺后缀的运行期 identity
  fail closed（不猜归属），模板骨架 `GTROW-…`（非 MINTED）原样放行。

只有一张表时与引擎逐字节同口径（直接返回引擎结果）。
"""
from __future__ import annotations

from dataclasses import replace as dc_replace
from typing import Any, Sequence

from app.services.workpaper_sync.models import SyncDomainError

__all__ = [
    "SharedStoreRegionError",
    "build_store_projection_shared",
    "merge_projection_into_store_rows_shared",
    "namespace_projection_rows",
]


class SharedStoreRegionError(SyncDomainError):
    """同 store 多区的行身份不合法（缺命名空间后缀 / stable key 缺段）。"""

    error_code = "sync_shared_store_region_identity_invalid"


def _projection(contract_like: Any, values: dict[str, Any], row_keys: dict[str, tuple[str, ...]]) -> Any:
    from app.services.workpaper_sync.adapters.base import Projection

    return Projection(
        contract_id=contract_like.contract_id,
        semantic_version=contract_like.semantic_version,
        document_type=contract_like.document_type,
        values=values,
        row_keys=row_keys,
    )


def projection_slice_for(projection: Any, table_key: str) -> Any:
    """只属于该受管表的切片（多表合回时必须切，否则别表的列会被合进本表）。"""
    prefix = f"{table_key}/"
    return _projection(
        projection,
        {k: v for k, v in dict(projection.values).items() if str(k).startswith(prefix)},
        {table_key: tuple(dict(projection.row_keys).get(table_key, ()))},
    )


def namespace_projection_rows(projection: Any, table_key: str, *, encode: bool) -> Any:
    """同 store sibling 表的物理 rowId 加 / 去可逆命名空间（stable key `{table_key}/{row_id}/{field_id}`）。"""
    suffix = f"~gt:{table_key}"
    prefix = f"{table_key}/"

    def map_id(rid: str) -> str:
        if encode:
            return rid if rid.endswith(suffix) else rid + suffix
        if rid.endswith(suffix):
            return rid[: -len(suffix)]
        # 模板预置骨架身份不是 store 投影产生的，原样交给 ghost-row 过滤；运行期 identity 缺后缀不猜
        if rid.startswith("GTROW-") and not rid.startswith("GTROW-MINTED-"):
            return rid
        raise SharedStoreRegionError(f"table {table_key!r} 的 sibling identity {rid!r} 缺命名空间后缀 {suffix!r}")

    values: dict[str, Any] = {}
    for key, value in dict(projection.values).items():
        text = str(key)
        if not text.startswith(prefix):
            values[text] = value
            continue
        rid, sep, field_id = text[len(prefix):].partition("/")
        if not sep:
            raise SharedStoreRegionError(f"stable key {text!r} 缺 field_id 段")
        mapped = map_id(rid)
        values[f"{prefix}{mapped}/{field_id}"] = (
            dc_replace(value, row_key=mapped) if getattr(value, "row_key", None) is not None else value
        )
    rows = tuple(map_id(str(r)) for r in dict(projection.row_keys).get(table_key, ()))
    return _projection(projection, values, {table_key: rows})


def build_store_projection_shared(
    hits: Sequence[Any], payload: Any, *, contract: Any, limits: Any | None = None
) -> Any:
    """`hits` = 共用同一 store item 的受管表 spec（顺序即主 / 兄弟）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection as _engine

    if len(hits) == 1:
        return _engine(hits[0], payload, contract=contract, limits=limits)
    values: dict[str, Any] = {}
    row_keys: dict[str, tuple[str, ...]] = {}
    for index, spec in enumerate(hits):
        proj = _engine(spec, payload, contract=contract, limits=limits)
        if index:
            proj = namespace_projection_rows(proj, spec.table_key, encode=True)
        values.update(proj.values)
        row_keys.update(dict(proj.row_keys))
    return _projection(contract, values, row_keys)


def merge_projection_into_store_rows_shared(
    hits: Sequence[Any], *, projection: Any, base_rows: list
) -> tuple[list, int, int, set[str]]:
    """按表切片后**依次**合进同一组行（各区共享行身份，后一张表在前一张的结果上补自己那组字段）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine,
    )

    if len(hits) == 1:
        return _engine(hits[0], projection=projection, base_rows=base_rows)
    rows: list = list(base_rows)
    added = removed = 0
    touched: set[str] = set()
    for index, spec in enumerate(hits):
        sliced = projection_slice_for(projection, spec.table_key)
        if index:
            sliced = namespace_projection_rows(sliced, spec.table_key, encode=False)
        rows, a, r, t = _engine(spec, projection=sliced, base_rows=rows)
        added, removed = max(added, a), max(removed, r)
        touched |= set(t)
    return rows, added, removed, touched
