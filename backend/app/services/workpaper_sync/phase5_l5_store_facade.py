# -*- coding: utf-8 -*-
"""L5 的 store 投影/合并门面 —— 三区同键（照 `phase5_g9_store_facade`）。

spec: l5-true-bidirectional-2026-10-01 · T4

═══ 为什么 L5 需要它，而 L7 不需要 ═══

L7 是单受管区，`build_store_projection`/`merge` 直接走框架层单 spec 函数即可。
L5 的 `明细表L5-2` 有**三个受管区**（R11:15 售后租回 / R18:22 分期付款 / R24:24 其他），
区之间夹着小计/合计/标题静态行，前端把三区的行存在**同一个** `L5-L5-2-rows` 数组、
用 `section` 字段标记区归属（照 G9）。平台既有多区范式（`phase5_d3_04_analysis`）是
「一区一个 store_item_id」—— 那要求前端拆键，而 L5 的单键单数组已是前端持久化契约。
⇒ 三 spec 共享 store 键 + `row_section_field='section'` 过滤，本模块按「遍历三段」组合：

* :func:`build_store_projection` —— 缺省投影**全部三段**并合并成一个 `Projection`
  （生产路径 `store_projection_response.py` / `projection_first_publication.py` 只传一份 payload、
  不带段参数；只投区①会静默丢掉区②③的行）；
* :func:`merge_projection_into_store_rows` —— 三段**顺序穿线**（上段 merged 作下段 base_rows）；
* :func:`iter_store_rows` —— 缺省串联三段（各段内部按 `section` 过滤）。

三者都接受 `section=` 显式指定单段，供逐段判据使用。

🔴 本模块对主模块的引用一律**函数体内惰性 import**（避免与主模块末尾重导出构成循环）。
"""
from __future__ import annotations

import json
from typing import Any, Iterator, Mapping, Sequence

__all__ = [
    "specs_for",
    "build_store_projection",
    "merge_projection_into_store_rows",
    "iter_store_rows",
    "split_store_payload_by_section",
]


def _provider() -> Any:
    from app.services.workpaper_sync import phase5_l5_long_term_payables as _p

    return _p


def specs_for(section: str | None, store_item_id: str | None) -> tuple[Any, ...]:
    """解析本次操作覆盖哪些段（section=None ⇒ 全三段；指定 ⇒ 仅该段）。"""
    p = _provider()
    specs = tuple(p.SPECS)
    if not specs:
        raise p.EntrySelectionError("L5 当前无受管 sheet")
    if store_item_id is not None:
        specs = tuple(s for s in specs if s.store_item_id == store_item_id)
        if not specs:
            raise p.EntrySelectionError(
                f"store item {store_item_id!r} 不在 L5 受管清单里；"
                f"已受管：{sorted({s.store_item_id for s in p.SPECS})}"
            )
    if section is None:
        return specs
    picked = tuple(s for s in specs if s.row_section_value == section)
    if not picked:
        raise p.EntrySelectionError(
            f"section {section!r} 不在 L5 受管段里；"
            f"已受管：{[s.row_section_value for s in specs]}"
        )
    return picked


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: Any,
    limits: Any | None = None,
    store_item_id: str | None = None,
    section: str | None = None,
) -> Any:
    """HTML store 载荷 → `Projection`（**缺省合并三段**）。

    🔴 签名刚性：`payload` 第一个位置参数、其余走关键字（零回归门按
    `mod.build_store_projection(rows, contract=contract)` 调用）。
    🔴 缺省投影全部三段：生产调用点只传一份 payload、无段参数；只投区①会假绿。
    """
    from app.services.workpaper_sync.adapters.base import Projection
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableStorePayloadError,
        build_store_projection as _engine,
    )

    p = _provider()
    specs = specs_for(section, store_item_id)
    values: dict[str, Any] = {}
    row_keys: dict[str, Any] = {}
    first: Any = None
    for spec in specs:
        try:
            proj = _engine(spec, payload, contract=contract, limits=limits)
        except RowTableStorePayloadError as exc:
            raise p.StorePayloadError(str(exc)) from exc
        if first is None:
            first = proj
        collision = values.keys() & proj.values.keys()
        if collision:
            raise p.StorePayloadError(
                f"L5 段 {spec.row_section_value!r} 的 projection 与前段 stable_key 相撞："
                f"{sorted(collision)[:3]} —— sheet 层 table_key 声明漂移"
            )
        values.update(proj.values)
        row_keys.update(proj.row_keys)
    assert first is not None
    return Projection(
        contract_id=first.contract_id,
        semantic_version=first.semantic_version,
        document_type=first.document_type,
        values=values,
        row_keys=row_keys,
    )


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
    store_item_id: str | None = None,
    section: str | None = None,
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """projection → HTML store 行（**三段顺序穿线**，含幽灵行防护 + 新增行补段归属）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    rows: list[Mapping[str, Any]] = list(base_rows)
    applied_total = 0
    visited_total = 0
    touched_all: set[str] = set()
    for spec in specs_for(section, store_item_id):
        merged, applied, visited, touched = _engine_merge(
            spec, projection=projection, base_rows=rows
        )
        rows = merged
        applied_total += applied
        visited_total += visited
        touched_all |= touched
    return [dict(r) for r in rows], applied_total, visited_total, touched_all


def iter_store_rows(
    payload: Any,
    *,
    store_item_id: str | None = None,
    section: str | None = None,
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """流式 `(row_identity, row)`；缺省**串联三段**（各段内部按 `section` 过滤）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        iter_store_rows as _engine_iter,
    )

    for spec in specs_for(section, store_item_id):
        yield from _engine_iter(spec, payload)


def split_store_payload_by_section(
    payload: str | bytes | Sequence[Any],
) -> dict[str, list[Mapping[str, Any]]]:
    """按 `section` 把一份 store 载荷拆成三段（排障/判据用，不在生产路径上）。"""
    p = _provider()
    if isinstance(payload, (str, bytes)):
        text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        parsed = json.loads(text) if text.strip() else []
    else:
        parsed = list(payload)
    if not isinstance(parsed, list):
        raise p.StorePayloadError(
            f"{p.STORE_ITEM_ID} 载荷根形态必须是数组，实得 {type(parsed).__name__}"
        )
    known = {s.row_section_value for s in p.SPECS}
    buckets: dict[str, list[Mapping[str, Any]]] = {k: [] for k in sorted(known)}
    buckets.setdefault("", [])
    for row in parsed:
        if not isinstance(row, Mapping):
            raise p.StorePayloadError(
                f"{p.STORE_ITEM_ID} 存在非对象行：{type(row).__name__}"
            )
        value = str(row.get("section") or "")
        buckets[value if value in known else ""].append(row)
    return buckets
