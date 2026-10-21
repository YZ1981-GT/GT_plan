"""通用有效定义解析 + 层级标签（R1.1 / R1.4，design §5）。

有效定义 = 本项目层 ?? 全局（精确作用范围 ?? ``*``）?? 系统预设。订阅模板已物化为本项目层行
（``base_origin='template'``），所以这里不单独查模板层。

层级标签：
* ``global`` —— 无本项目行，或本项目行与当前全局执行字段相同（跟随全局的副本）；
* ``template`` —— 本项目行来自订阅模板且未在本项目改过；
* ``project`` —— 本项目适配（与上游不同）；
* ``pinned`` —— 暂缓 / 冻结而固定在旧定义；
* ``preset`` —— 只有系统预设。
另有 ``pending``（有待确认事项）与 ``disabled``（本项目停用）两个独立标记。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formula_setting_models import FormulaSyncItem
from app.services.formula_settings.definitions import is_effectively_disabled, same_exec
from app.services.formula_settings.stores import DomainStore, SlotRecord, get_store

LAYER_LABELS: dict[str, str] = {
    "global": "全局",
    "template": "模板",
    "project": "本项目",
    "pinned": "暂缓采用",
    "preset": "系统预设",
}


@dataclass
class EffectiveSlot:
    slot_key: str
    label: str
    layer: str
    definition: dict | None
    upstream: SlotRecord | None
    local: SlotRecord | None
    pending: bool = False
    disabled: bool = False

    @property
    def structure(self) -> dict:
        for rec in (self.upstream, self.local):
            if rec is not None and rec.structure:
                return rec.structure
        return {}

    def to_dict(self) -> dict[str, Any]:
        up, lo = self.upstream, self.local
        return {
            "slot_key": self.slot_key,
            "label": self.label,
            "layer": self.layer,
            "layer_label": LAYER_LABELS.get(self.layer, self.layer),
            "definition": _public(self.definition),
            "disabled": self.disabled,
            "pending": self.pending,
            "structure": self.structure,
            "global_definition": _public(up.definition) if up is not None and up.layer != "preset" else None,
            "global_version": up.version if up is not None and up.layer != "preset" else None,
            "preset_definition": _public(up.definition) if up is not None and up.layer == "preset" else None,
            "local_definition": _public(lo.definition) if lo is not None else None,
            "local_version": lo.version if lo is not None else None,
            "base_definition": _public(lo.base_definition) if lo is not None else None,
            "base_version": lo.base_version if lo is not None else None,
            "base_origin": lo.base_origin if lo is not None else None,
            "base_template_id": str(lo.base_template_id) if lo is not None and lo.base_template_id else None,
            "pinned": bool(lo.pinned) if lo is not None else False,
        }


def _public(definition: dict | None) -> dict | None:
    if definition is None:
        return None
    return {k: v for k, v in definition.items() if k != "_structure"}


def layer_of(domain: str, local: SlotRecord | None, upstream: SlotRecord | None) -> str:
    if local is None:
        return "preset" if upstream is not None and upstream.layer == "preset" else "global"
    if local.pinned:
        return "pinned"
    if local.base_origin == "template":
        return "template" if same_exec(domain, local.definition, local.base_definition) else "project"
    if upstream is not None and same_exec(domain, local.definition, upstream.definition):
        return "preset" if upstream.layer == "preset" else "global"
    return "project"


async def upstream_records(db: AsyncSession, store: DomainStore, scope: str) -> dict[str, SlotRecord]:
    """作用范围 ``scope`` 下每个公式位的全局定义（无全局时为系统预设）。"""
    out: dict[str, SlotRecord] = {}
    for key, rec in (await store.system_presets(db, scope)).items():
        rec.layer = "preset"
        out[key] = rec
    out.update(await store.list_global(db, scope))
    return out


async def pending_slot_keys(db: AsyncSession, domain: str, project_id: uuid.UUID) -> set[str]:
    rows = await db.execute(sa.select(FormulaSyncItem.slot_key).where(
        FormulaSyncItem.project_id == project_id,
        FormulaSyncItem.domain == domain,
        FormulaSyncItem.status == "pending",
    ))
    return {r[0] for r in rows.all()}


async def effective_slots(db: AsyncSession, domain: str, project_id: uuid.UUID, *,
                          scope: str | None = None) -> dict[str, EffectiveSlot]:
    """本项目在 ``domain`` 上全部公式位的有效定义与层级。"""
    store = get_store(domain)
    scope = scope or await store.project_scope(db, project_id)
    upstream = await upstream_records(db, store, scope)
    local = await store.list_project(db, project_id)
    pending = await pending_slot_keys(db, domain, project_id)
    out: dict[str, EffectiveSlot] = {}
    for key in sorted(set(upstream) | set(local)):
        up, lo = upstream.get(key), local.get(key)
        definition = lo.definition if lo is not None else (up.definition if up is not None else None)
        label = (up.label if up is not None else None) or (lo.label if lo is not None else key)
        out[key] = EffectiveSlot(
            slot_key=key, label=label, layer=layer_of(domain, lo, up), definition=definition,
            upstream=up, local=lo, pending=key in pending,
            disabled=is_effectively_disabled(domain, definition) and up is not None
            and not is_effectively_disabled(domain, up.definition),
        )
    return out
