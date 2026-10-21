"""项目侧操作：保存本项目适配、恢复为全局、处理待确认（R5 / R6，design §7）。只 flush，路由 commit。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formula_setting_models import FormulaSyncItem
from app.services.formula_settings.audit import audit_project, change_entry
from app.services.formula_settings.definitions import get_spec, same_exec
from app.services.formula_settings.effective import upstream_records
from app.services.formula_settings.engine import lock_project
from app.services.formula_settings.errors import (
    Forbidden,
    FormulaSettingError,
    NotFound,
    SyncItemStale,
    VersionConflict,
    VersionRequired,
)
from app.services.formula_settings.pending import close_pending, find_pending
from app.services.formula_settings.projects import ProjectInfo, get_project
from app.services.formula_settings.stores import DomainStore, SlotRecord, get_store
from app.services.formula_settings.sync import Action, Resolution, resolve_pending


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def require_project(db: AsyncSession, domain: str, project_id: uuid.UUID, *,
                          writable: bool = True) -> ProjectInfo:
    project = await get_project(db, domain, project_id)
    if project is None:
        raise NotFound("项目不存在或已删除")
    if writable and project.frozen:
        raise Forbidden("项目已归档，公式定义保持归档时的状态，不能修改", status_code=423, code="PROJECT_ARCHIVED")
    return project


def _events(project_id: uuid.UUID, slots: list[str]) -> list[dict[str, Any]]:
    return [{"project_id": str(project_id), "slot_keys": slots}] if slots else []


# ── 保存本项目适配 ────────────────────────────────────────────────────────────


async def save_overrides(db: AsyncSession, *, domain: str, project_id: uuid.UUID,
                         items: list[Mapping[str, Any]], user_id: uuid.UUID | None,
                         source: str = "project_edit", action: str = "adapt") -> dict[str, Any]:
    """批量保存（单事务）。已有适配须带 ``expected_version``（本地修订号）做 CAS。"""
    get_spec(domain)
    project = await require_project(db, domain, project_id)
    store = get_store(domain)
    await lock_project(db, domain, project_id)
    upstream = await upstream_records(db, store, project.scope)
    local = await store.list_project(db, project_id)
    problems, saved, changed, audits = [], [], [], []
    plan: list[tuple[str, dict, SlotRecord | None, SlotRecord | None, Mapping[str, Any]]] = []
    for raw in items:
        slot = str(raw.get("slot_key") or "").strip()
        if not slot:
            raise FormulaSettingError("公式位不能为空")
        definition = raw.get("definition")
        if not isinstance(definition, Mapping):
            raise FormulaSettingError(f"公式位 {slot} 缺少定义")
        lo, up = local.get(slot), upstream.get(slot)
        ev = raw.get("expected_version")
        if lo is not None and ev is None:
            problems.append({"slot_key": slot, "reason": "required", "current_version": lo.version})
        elif lo is not None and int(ev) != lo.version:
            problems.append({"slot_key": slot, "reason": "conflict", "current_version": lo.version,
                             "expected_version": int(ev)})
        elif lo is None and ev not in (None, 0):
            problems.append({"slot_key": slot, "reason": "conflict", "current_version": None,
                             "expected_version": int(ev)})
        current = lo.definition if lo is not None else (up.definition if up is not None else {})
        merged = dict(definition) if definition.get("disabled") else {**(current or {}), **dict(definition)}
        plan.append((slot, merged, lo, up, raw))
    if problems:
        if any(p["reason"] == "required" for p in problems):
            raise VersionRequired("修改本项目公式必须带版本号，请刷新后重试", detail={"problems": problems})
        raise VersionConflict("本项目公式已被他人修改，请刷新后重试", detail={"problems": problems})
    for slot, merged, lo, up, raw in plan:
        before = lo.definition if lo is not None else (up.definition if up is not None else None)
        if lo is not None:
            base_def, base_ver, origin, tpl = lo.base_definition, lo.base_version, lo.base_origin, lo.base_template_id
            pinned = lo.pinned
        else:
            base_def = up.definition if up is not None else None
            base_ver = up.version if up is not None else None
            origin = ("preset" if up.layer == "preset" else "global") if up is not None else None
            tpl, pinned = None, False
        await store.write_project(db, project_id, slot, definition=merged, base_definition=base_def,
                                  base_version=base_ver, pinned=pinned, base_origin=origin, base_template_id=tpl,
                                  user_id=user_id, label=str(raw.get("label") or (up.label if up else "")),
                                  structure=dict(raw.get("structure") or {}) or None)
        item = await find_pending(db, project_id, domain, slot)
        if item is not None:
            item.local_definition = {k: v for k, v in merged.items() if k != "_structure"}
            item.updated_at = _now()
        saved.append(slot)
        if not same_exec(domain, before, merged):
            changed.append(slot)
        audits.append(change_entry(domain, slot, before, merged, effect=action,
                                   config_id=lo.row_id if lo is not None else None))
    await db.flush()
    await audit_project(db, user_id=user_id, project_id=project_id, domain=domain, action=action,
                        source=source, changes=audits)
    after = await store.list_project(db, project_id)
    return {"saved": [{"slot_key": s, "version": after[s].version if s in after else None} for s in saved],
            "events": _events(project_id, changed)}


# ── 恢复为全局 ────────────────────────────────────────────────────────────────


async def restore_global(db: AsyncSession, *, domain: str, project_id: uuid.UUID, slot_keys: list[str],
                         user_id: uuid.UUID | None) -> dict[str, Any]:
    """删除本项目适配，回到上游；来自订阅模板的公式位回到模板定义。待确认事项一并结案（adopt）。"""
    get_spec(domain)
    project = await require_project(db, domain, project_id)
    store = get_store(domain)
    await lock_project(db, domain, project_id)
    upstream = await upstream_records(db, store, project.scope)
    local = await store.list_project(db, project_id)
    restored, changed, audits = [], [], []
    for slot in dict.fromkeys(slot_keys):
        lo = local.get(slot)
        if lo is None:
            continue
        up = upstream.get(slot)
        template_def = None
        if lo.base_origin == "template" and lo.base_template_id is not None:
            from app.services.formula_settings.templates import current_template_definition

            template_def = await current_template_definition(db, project_id, domain, slot)
        if template_def is not None:
            target = template_def["definition"]
            await store.write_project(db, project_id, slot, definition=target, base_definition=target,
                                      base_version=template_def["version"], pinned=False, base_origin="template",
                                      base_template_id=template_def["template_id"], user_id=user_id,
                                      label=lo.label)
        else:
            target = up.definition if up is not None else None
            await store.delete_project(db, project_id, slot)
        await close_pending(db, project_id, domain, [slot], status="resolved", resolution="adopt", user_id=user_id)
        restored.append(slot)
        if not same_exec(domain, lo.definition, target):
            changed.append(slot)
        audits.append(change_entry(domain, slot, lo.definition, target, effect="restore", config_id=lo.row_id))
    await db.flush()
    await audit_project(db, user_id=user_id, project_id=project_id, domain=domain, action="restore",
                        source="project_restore", changes=audits)
    return {"restored": restored, "events": _events(project_id, changed)}


# ── 待确认事项 ────────────────────────────────────────────────────────────────


async def resolve_items(db: AsyncSession, *, project_id: uuid.UUID, resolutions: list[Mapping[str, Any]],
                        user_id: uuid.UUID | None) -> dict[str, Any]:
    """逐条处理：采用最新上游 / 保留本项目 / 手工修改。事项已被新发布更新或已结案 → 409。"""
    if not resolutions:
        raise FormulaSettingError("没有要处理的事项")
    ids = []
    for r in resolutions:
        try:
            ids.append(uuid.UUID(str(r.get("item_id"))))
        except (TypeError, ValueError):
            raise FormulaSettingError("事项编号格式不正确") from None
    rows = (await db.execute(sa.select(FormulaSyncItem).where(FormulaSyncItem.id.in_(ids)))).scalars().all()
    by_id = {r.id: r for r in rows}
    domains = sorted({r.domain for r in rows})
    for d in domains:
        await lock_project(db, d, project_id)
    events: dict[str, list[str]] = {}
    done, audits_by_domain = [], {}
    for raw, item_id in zip(resolutions, ids):
        item = by_id.get(item_id)
        if item is None or item.project_id != project_id:
            raise NotFound("待确认事项不存在")
        await db.refresh(item)
        expected = raw.get("upstream_version")
        if item.status != "pending" or (expected is not None and item.upstream_version != int(expected)):
            raise SyncItemStale("该事项已被新的发布更新或已处理，请刷新后重试",
                                detail={"item_id": str(item.id), "status": item.status,
                                        "upstream_version": item.upstream_version})
        await require_project(db, item.domain, project_id)
        choice = Resolution(str(raw.get("choice") or ""))
        store = get_store(item.domain)
        lo = (await store.list_project(db, project_id)).get(item.slot_key)
        final = await _resolve_one(db, store, item, choice, lo, raw.get("custom_definition"), user_id)
        item.status, item.resolution = "resolved", choice.value
        item.resolved_definition = {k: v for k, v in final.items() if k != "_structure"} if final else None
        item.resolved_by, item.resolved_at, item.updated_at = user_id, _now(), _now()
        before = lo.definition if lo is not None else None
        if not same_exec(item.domain, before, final):
            events.setdefault(item.domain, []).append(item.slot_key)
        audits_by_domain.setdefault(item.domain, []).append(
            change_entry(item.domain, item.slot_key, before, final, effect=f"resolve_{choice.value}",
                         config_id=lo.row_id if lo is not None else None, sync_item_id=item.id))
        done.append(str(item.id))
    await db.flush()
    from app.services.formula_settings.template_sync import refresh_subscription

    for d, tpl_id in {(r.domain, r.upstream_template_id) for r in rows if r.upstream_origin == "template"}:
        await refresh_subscription(db, project_id, d, tpl_id)  # 暂缓的订阅处理完后跟上模板当前版本
    for d, entries in audits_by_domain.items():
        await audit_project(db, user_id=user_id, project_id=project_id, domain=d, action="resolve_pending",
                            source="project_resolve", changes=entries)
    return {"resolved": done,
            "events": [{"project_id": str(project_id), "domain": d, "slot_keys": s} for d, s in events.items()]}


async def _resolve_one(db: AsyncSession, store: DomainStore, item: FormulaSyncItem, choice: Resolution,
                       lo: SlotRecord | None, custom: Any, user_id: uuid.UUID | None) -> dict | None:
    """返回处理后的有效定义。"""
    domain, pid, slot = store.domain, item.project_id, item.slot_key
    if choice is Resolution.CUSTOM and not isinstance(custom, Mapping):
        raise FormulaSettingError("手工修改必须提供公式定义")
    if item.upstream_origin == "project":
        # 来自其他项目的推送：本项目的基线仍是自己的上游，不随推送方改变
        if choice is Resolution.KEEP:
            return lo.definition if lo is not None else None
        target = dict(custom) if choice is Resolution.CUSTOM else dict(item.upstream_definition or {})
        if lo is None and item.upstream_definition is None and choice is Resolution.ADOPT:
            return None
        project = await get_project(db, domain, pid)
        up = (await upstream_records(db, store, project.scope)).get(slot) if project else None
        await store.write_project(
            db, pid, slot, definition=target,
            base_definition=lo.base_definition if lo is not None else (up.definition if up else None),
            base_version=lo.base_version if lo is not None else (up.version if up else None),
            pinned=False, base_origin=(lo.base_origin if lo is not None else "global"),
            base_template_id=lo.base_template_id if lo is not None else None,
            user_id=user_id, label=item.slot_label or "")
        return target
    effect = resolve_pending(domain, choice, upstream=item.upstream_definition,
                             upstream_version=item.upstream_version, local=lo.local_state() if lo else None,
                             custom_definition=dict(custom) if isinstance(custom, Mapping) else None)
    if effect.action is Action.DELETE_LOCAL:
        if lo is not None:
            await store.delete_project(db, pid, slot)
        return None
    if effect.action is Action.SET_LOCAL:
        await store.write_project(db, pid, slot, definition=dict(effect.local_definition or {}),
                                  base_definition=effect.base_definition, base_version=effect.base_version,
                                  pinned=False, base_origin=item.upstream_origin,
                                  base_template_id=item.upstream_template_id, user_id=user_id,
                                  label=item.slot_label or "")
        return dict(effect.local_definition or {})
    return lo.definition if lo is not None else None
