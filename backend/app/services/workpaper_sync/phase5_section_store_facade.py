# -*- coding: utf-8 -*-
"""多区行表 store 门面：一个 store item、行按字段分到多个受管区（可选 dict 外壳）—— **按 provider 绑定**。

spec oo-writeback-template-parity-closure R3 批 B3。

原先只有 G9 一份（``phase5_g9_store_facade``），``_provider()`` 写死 G9；G3 / G4 / G5 / G6 原样重导出它 ⇒
出方向按 G9 的 spec 投影（G3 行没有 G9 的 ``section`` 字段 ⇒ 恒空），回写按 G9 的表键合并（一格都合不进），
带 store item 调用就抛「不在 G9 受管清单里」。G1 自己的门面按 store item 取**第一条** spec（三区共用一个键 ⇒
只通区①）。本模块把门面做成绑定对象：spec 清单、错误类型、STORE_ITEM_ID 都从被绑定的 provider 现取。

* 多区：``iter_store_rows`` / 投影 / 合并逐区穿线（区由 spec 的 ``row_section_field`` / ``row_section_value``
  过滤，见 ``phase5_row_table_sheet``）；单区 provider 也适用（只有一条 spec）。
* dict 外壳（``rows_key``）：前端 store 是 ``{rows: [...], 其他键}``（G6-5 ``{rows, conclusion}``）时，投影只取
  ``rows``、回写走 ``merge_projection_into_store_state`` 只换行数组、其余键原样保留。``iter_store_rows`` 不拆外壳
  （采纳覆盖按行数组枚举，对象载荷照旧 fail visible，不会把外壳写丢）。
"""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence


@dataclass(frozen=True)
class SectionStoreFacade:
    #: provider 模块名（``app.services.workpaper_sync.<name>``）
    provider_module: str
    #: dict 外壳里的行数组键；None ⇒ 载荷本身就是行数组
    rows_key: str | None = None

    def _provider(self) -> Any:
        return importlib.import_module(f"app.services.workpaper_sync.{self.provider_module}")

    def specs_for(self, section: str | None = None, store_item_id: str | None = None) -> tuple[Any, ...]:
        """本次操作覆盖哪些区：缺省全部受管区（只投一区会静默丢别区的行）；给 section 只取该区。"""
        p = self._provider()
        specs = tuple(p.managed_row_table_specs())
        if not specs:
            raise p.EntrySelectionError(f"{p.ADAPTER_ID} 当前无受管 sheet")
        if store_item_id is not None:
            specs = tuple(s for s in specs if s.store_item_id == store_item_id)
            if not specs:
                raise p.EntrySelectionError(
                    f"store item {store_item_id!r} 不在 {p.ADAPTER_ID} 受管清单里；"
                    f"已受管：{sorted(p.all_store_item_ids())}"
                )
        if section is None:
            return specs
        picked = tuple(s for s in specs if s.row_section_value == section)
        if not picked:
            raise p.EntrySelectionError(
                f"section {section!r} 不在 {p.ADAPTER_ID} 受管区里；已受管：{[s.row_section_value for s in specs]}"
            )
        return picked

    def rows_of(self, payload: Any) -> Any:
        """载荷 → 行数组（无外壳原样返回；有外壳按名取，键缺失 = 空表，值不是数组原样交给引擎 fail closed）。"""
        if self.rows_key is None:
            return payload
        parsed = payload
        if isinstance(payload, (str, bytes, bytearray)):
            text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
            parsed = json.loads(text) if text.strip() else {}
        if isinstance(parsed, Mapping):
            return parsed.get(self.rows_key, [])
        return parsed

    def build_store_projection(
        self,
        payload: str | bytes | Sequence[Any],
        *,
        contract: Any,
        limits: Any | None = None,
        store_item_id: str | None = None,
        section: str | None = None,
    ) -> Any:
        """HTML store 载荷 → ``Projection``（缺省合并全部受管区；``payload`` 必须是第一个位置参数，见 golden 门）。"""
        from app.services.workpaper_sync.adapters.base import Projection
        from app.services.workpaper_sync.phase5_row_table_sheet import build_store_projection as _engine

        rows = self.rows_of(payload)
        values: dict[str, Any] = {}
        row_keys: dict[str, Any] = {}
        first: Any = None
        for spec in self.specs_for(section, store_item_id):
            proj = _engine(spec, rows, contract=contract, limits=limits)
            if first is None:
                first = proj
            collision = values.keys() & proj.values.keys()
            if collision:
                raise self._provider().StorePayloadError(
                    f"区 {spec.row_section_value!r} 的 projection 与前区 stable_key 相撞："
                    f"{sorted(collision)[:3]} —— sheet 层 table_key 声明漂移"
                )
            values.update(proj.values)
            row_keys.update(proj.row_keys)
        return Projection(
            contract_id=first.contract_id,
            semantic_version=first.semantic_version,
            document_type=first.document_type,
            values=values,
            row_keys=row_keys,
        )

    def merge_projection_into_store_rows(
        self,
        *,
        projection: Any,
        base_rows: list[Mapping[str, Any]],
        store_item_id: str | None = None,
        section: str | None = None,
    ) -> tuple[list[dict[str, Any]], int, int, set[str]]:
        """projection → store 行（逐区穿线：上一区的合并结果喂下一区，各区只动本表键，别区行原样保留）。"""
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            merge_projection_into_store_rows as _engine_merge,
        )

        rows: list[Mapping[str, Any]] = list(base_rows)
        applied_total = visited_total = 0
        touched_all: set[str] = set()
        for spec in self.specs_for(section, store_item_id):
            rows, applied, visited, touched = _engine_merge(spec, projection=projection, base_rows=rows)
            applied_total += applied
            visited_total += visited
            touched_all |= touched
        return [dict(r) for r in rows], applied_total, visited_total, touched_all

    def merge_projection_into_store_state(
        self,
        *,
        projection: Any,
        base_state: Mapping[str, Any] | None,
        store_item_id: str | None = None,
    ) -> tuple[dict[str, Any], int, int]:
        """dict 外壳的回写门面（``store_mirror`` 的 state 分支按名调用）：只换行数组，其余键原样保留。"""
        if self.rows_key is None:
            raise self._provider().StorePayloadError("本 store 不是 dict 外壳，回写应走行数组门面")
        state: dict[str, Any] = dict(base_state or {})
        base_rows = state.get(self.rows_key)
        rows, applied, visited, _touched = self.merge_projection_into_store_rows(
            projection=projection,
            base_rows=list(base_rows) if isinstance(base_rows, list) else [],
            store_item_id=store_item_id,
        )
        state[self.rows_key] = rows
        return state, applied, visited

    def iter_store_rows(
        self,
        payload: Any,
        *,
        store_item_id: str | None = None,
        section: str | None = None,
    ) -> Iterator[tuple[str, Mapping[str, Any]]]:
        """流式 ``(row_identity, row)``，缺省串联全部受管区（不拆 dict 外壳，见模块 docstring）。"""
        from app.services.workpaper_sync.phase5_row_table_sheet import iter_store_rows as _engine_iter

        for spec in self.specs_for(section, store_item_id):
            yield from _engine_iter(spec, payload)

    def split_store_payload_by_section(
        self, payload: str | bytes | Sequence[Any]
    ) -> dict[str, list[Mapping[str, Any]]]:
        """按区字段把一份载荷拆开（排障 / 判据用，不在生产路径上）；未登记的区值归 ``""`` 桶，不静默丢。"""
        p = self._provider()
        rows = self.rows_of(payload)
        if isinstance(rows, (str, bytes)):
            text = rows.decode("utf-8") if isinstance(rows, bytes) else rows
            rows = json.loads(text) if text.strip() else []
        parsed = list(rows) if isinstance(rows, list) else rows
        if not isinstance(parsed, list):
            raise p.StorePayloadError(f"{p.STORE_ITEM_ID} 载荷根形态必须是数组，实得 {type(parsed).__name__}")
        specs = self.specs_for()
        field = next((s.row_section_field for s in specs if s.row_section_field), "")
        known = {s.row_section_value for s in specs if s.row_section_field}
        buckets: dict[str, list[Mapping[str, Any]]] = {k: [] for k in sorted(known)}
        buckets.setdefault("", [])
        for row in parsed:
            if not isinstance(row, Mapping):
                raise p.StorePayloadError(f"{p.STORE_ITEM_ID} 存在非对象行：{type(row).__name__}")
            value = str(row.get(field) or "") if field else ""
            buckets[value if value in known else ""].append(row)
        return buckets
