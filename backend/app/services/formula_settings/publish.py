"""全局设置：影响预览与发布（R2 / R3 / R4，design §6）。只 flush，路由 commit。

发布步骤：域排他锁 → 请求号幂等 → 逐公式位 CAS（缺版本 428、不一致 409，整批不写）→
对使用该作用范围的项目逐（项目, 公式位）分类 → 写全局（版本 +1）→ 按决策写各项目 →
待确认事项 → 发布记录 → 审计（全局一条 + 每项目）。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formula_setting_models import FormulaPublish
from app.services.formula_settings.audit import audit_global, audit_project, change_entry
from app.services.formula_settings.definitions import ANY_SCOPE, get_spec, is_disabled, normalize
from app.services.formula_settings.engine import (
    TEMPLATE_SKIPPED,
    ApplyOutcome,
    Decisions,
    PlanItem,
    apply_effect,
    changed_slots,
    decide_item,
    lock_domain,
    summarize,
)
from app.services.formula_settings.errors import FormulaSettingError, VersionConflict, VersionRequired
from app.services.formula_settings.projects import ProjectInfo, list_projects
from app.services.formula_settings.stores import DomainStore, SlotRecord, get_store

PUBLISH_SOURCES = ("global_edit", "promote", "direct_edit", "master_sync", "template_promote", "candidate", "seed")


@dataclass
class SlotChange:
    slot_key: str
    definition: dict | None
    expected_version: int | None = None
    label: str = ""
    structure: dict | None = None

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "SlotChange":
        slot = str(raw.get("slot_key") or "").strip()
        if not slot:
            raise FormulaSettingError("公式位不能为空")
        definition = raw.get("definition")
        if definition is not None and not isinstance(definition, Mapping):
            raise FormulaSettingError(f"公式位 {slot} 的定义格式不正确")
        ev = raw.get("expected_version")
        return cls(slot, dict(definition) if definition is not None else None,
                   int(ev) if ev is not None else None, str(raw.get("label") or ""),
                   dict(raw.get("structure") or {}) or None)


def _same_full(domain: str, a: Mapping | None, b: Mapping | None) -> bool:
    return normalize(domain, a) == normalize(domain, b)


@dataclass
class _Context:
    domain: str
    scope: str
    store: DomainStore
    changes: list[SlotChange]
    current: dict[str, SlotRecord]          # 发布作用范围的现行全局行（精确）
    projects: list[ProjectInfo]
    items: list[PlanItem]


async def _build(db: AsyncSession, domain: str, scope: str, raw_changes: list[Mapping[str, Any]]) -> _Context:
    store = get_store(domain)
    if not store.supports_any_scope and scope == ANY_SCOPE:
        raise FormulaSettingError(f"{get_spec(domain).label}没有通用作用范围，请选择具体准则")
    changes = [SlotChange.parse(c) for c in raw_changes]
    seen: set[str] = set()
    for ch in changes:
        if ch.slot_key in seen:
            raise FormulaSettingError(f"公式位重复：{ch.slot_key}")
        seen.add(ch.slot_key)
    current = await store.list_global_exact(db, scope)
    for ch in changes:
        if ch.definition is None:
            continue
        if is_disabled(ch.definition):
            raise FormulaSettingError(f"全局设置不能停用公式位 {ch.slot_key}；不再需要请删除该公式位")
        rec = current.get(ch.slot_key)
        if rec is not None:  # 只给出部分字段时，其余字段沿用现行全局（补丁语义）
            ch.definition = {**(rec.definition or {}), **ch.definition}
    # 与现行全局完全相同（含说明字段）或删除不存在的公式位 → 无变化，不写不传播
    effective_changes = [
        ch for ch in changes
        if not (_same_full(domain, ch.definition, current[ch.slot_key].definition) if ch.slot_key in current
                else ch.definition is None)
    ]
    projects = await list_projects(db, domain, scope=scope)
    items = await _plan(db, store, scope, effective_changes, current, projects)
    return _Context(domain, scope, store, effective_changes, current, projects, items)


async def _plan(db: AsyncSession, store: DomainStore, scope: str, changes: list[SlotChange],
                current: dict[str, SlotRecord], projects: list[ProjectInfo]) -> list[PlanItem]:
    if not changes or not projects:
        return []
    domain = store.domain
    star = await store.list_global_exact(db, ANY_SCOPE) if store.supports_any_scope and scope != ANY_SCOPE else {}
    exact_by_scope: dict[str, dict[str, SlotRecord]] = {}
    presets_by_scope: dict[str, dict[str, SlotRecord]] = {}
    for ps in {p.scope for p in projects}:
        exact_by_scope[ps] = current if ps == scope else await store.list_global_exact(db, ps)
        presets_by_scope[ps] = await store.system_presets(db, ps)
    star_all = current if scope == ANY_SCOPE else star
    locals_by_project = await store.list_project_many(db, [p.id for p in projects])

    items: list[PlanItem] = []
    for p in projects:
        exact_ps, presets = exact_by_scope[p.scope], presets_by_scope[p.scope]
        for ch in changes:
            slot = ch.slot_key
            if scope == ANY_SCOPE and p.scope != ANY_SCOPE and slot in exact_ps:
                continue  # 该项目作用范围有精确全局行，通用行变化与它无关
            old_rec = exact_ps.get(slot) or star_all.get(slot) or presets.get(slot)
            if ch.definition is not None:
                new_def, new_ver, new_origin, from_change = ch.definition, None, "global", True
            else:
                fallback = (star_all.get(slot) if scope != ANY_SCOPE else None) or presets.get(slot)
                new_def = fallback.definition if fallback else None
                new_ver = fallback.version if fallback else None
                new_origin = "preset" if fallback is not None and fallback.layer == "preset" else "global"
                from_change = fallback is None
            cur = current.get(slot)
            structure = dict(ch.structure or (cur.structure if cur else {}) or (old_rec.structure if old_rec else {}))
            local = locals_by_project.get(p.id, {}).get(slot)
            item = PlanItem(
                project=p, slot_key=slot,
                label=ch.label or (cur.label if cur else "") or (local.label if local else "") or slot,
                old_up=old_rec.definition if old_rec else None,
                old_version=old_rec.version if old_rec else None,
                old_origin="preset" if old_rec is not None and old_rec.layer == "preset" else "global",
                new_up=new_def, new_version=new_ver, new_origin=new_origin, local=local, structure=structure,
                version_from_change=from_change,
            )
            if local is not None and local.base_origin == "template":
                item.skipped = TEMPLATE_SKIPPED
            else:
                item.classify(domain)
            items.append(item)
    return items


def _predicted_version(current: dict[str, SlotRecord], slot: str) -> int:
    rec = current.get(slot)
    return (rec.version or 1) + 1 if rec is not None else 1


def _check_versions(ctx: _Context) -> list[dict[str, Any]]:
    problems = []
    for ch in ctx.changes:
        rec = ctx.current.get(ch.slot_key)
        if rec is None:
            if ch.expected_version not in (None, 0):
                problems.append({"slot_key": ch.slot_key, "expected_version": ch.expected_version,
                                 "current_version": None, "reason": "deleted"})
        elif ch.expected_version is None:
            problems.append({"slot_key": ch.slot_key, "expected_version": None,
                             "current_version": rec.version, "reason": "required"})
        elif ch.expected_version != rec.version:
            problems.append({"slot_key": ch.slot_key, "expected_version": ch.expected_version,
                             "current_version": rec.version, "reason": "conflict"})
    return problems


def _change_rows(ctx: _Context, versions: Mapping[str, int] | None = None) -> list[dict[str, Any]]:
    rows = []
    for ch in ctx.changes:
        rec = ctx.current.get(ch.slot_key)
        rows.append({
            "slot_key": ch.slot_key,
            "label": ch.label or (rec.label if rec else ch.slot_key),
            "old": rec.definition if rec else None,
            "new": ch.definition,
            "old_version": rec.version if rec else None,
            "new_version": (versions or {}).get(ch.slot_key, _predicted_version(ctx.current, ch.slot_key)),
            "deleted": ch.definition is None,
        })
    return rows


async def preview_global(db: AsyncSession, *, domain: str, scope: str,
                         changes: list[Mapping[str, Any]]) -> dict[str, Any]:
    """只读：不取锁、不写库；同一请求重复预览结果相同（R3.3）。"""
    ctx = await _build(db, domain, scope, changes)
    for it in ctx.items:
        if it.version_from_change:
            it.new_version = _predicted_version(ctx.current, it.slot_key)
    summary = summarize(ctx.items, ctx.projects)
    return {
        "domain": domain,
        "scope": scope,
        "changes": _change_rows(ctx),
        "version_problems": _check_versions(ctx),
        "summary": summary,
        "items": [it.to_dict(domain) for it in ctx.items if not (it.category and it.category.value == "inherit")],
    }


async def _replay(db: AsyncSession, request_id: str | None) -> FormulaPublish | None:
    if not request_id:
        return None
    return (await db.execute(sa.select(FormulaPublish).where(FormulaPublish.request_id == request_id))).scalars().first()


def _raise_versions(problems: list[dict[str, Any]]) -> None:
    if not problems:
        return
    if any(p["reason"] == "required" for p in problems):
        raise VersionRequired("修改已有全局公式必须带版本号，请刷新后重试", detail={"problems": problems})
    raise VersionConflict("全局公式已被他人修改，请刷新后重试", detail={"problems": problems})


async def publish_global(db: AsyncSession, *, domain: str, scope: str, changes: list[Mapping[str, Any]],
                         user_id: uuid.UUID | None, decisions: Decisions | None = None,
                         request_id: str | None = None, source: str = "global_edit",
                         source_project_id: uuid.UUID | None = None, note: str | None = None) -> dict[str, Any]:
    decisions = decisions or Decisions()
    get_spec(domain)
    await lock_domain(db, domain)
    replay = await _replay(db, request_id)
    if replay is not None:
        return {"publish_id": str(replay.id), "idempotent": True, "domain": replay.domain, "scope": replay.scope,
                "summary": replay.summary, "versions": {c["slot_key"]: c.get("new_version")
                                                        for c in (replay.change_set or [])}, "events": []}
    ctx = await _build(db, domain, scope, changes)
    _raise_versions(_check_versions(ctx))
    publish_id = uuid.uuid4()
    store = ctx.store
    versions: dict[str, int] = {}
    for ch in ctx.changes:
        versions[ch.slot_key] = await store.write_global(db, scope, ch.slot_key, ch.definition, user_id=user_id,
                                                         label=ch.label, structure=ch.structure)
    for it in ctx.items:
        if it.version_from_change:
            it.new_version = versions.get(it.slot_key)
    outcomes: dict[str, ApplyOutcome] = {}
    audits: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for it in ctx.items:
        if it.skipped:
            continue
        effect = decide_item(domain, it, decisions)
        out = await apply_effect(db, store, it, effect, publish_id=publish_id, user_id=user_id)
        outcomes[it.key] = out
        if out.audit is not None:
            audits.setdefault(it.project.id, []).append(out.audit)
    summary = summarize(ctx.items, ctx.projects, outcomes)
    change_set = _change_rows(ctx, versions)
    db.add(FormulaPublish(
        id=publish_id, domain=domain, scope=scope, target="global", source=source,
        source_project_id=source_project_id, request_id=request_id, status="published",
        change_set=change_set, summary=summary, note=note, published_by=user_id,
    ))
    await db.flush()
    await audit_global(db, user_id=user_id, domain=domain, scope=scope, action="formula.global_published",
                       resource_id=publish_id, details={
                           "source": source, "publish_id": str(publish_id), "note": note or "",
                           "changes": [change_entry(domain, c["slot_key"], c["old"], c["new"],
                                                    old_version=c["old_version"], new_version=c["new_version"])
                                       for c in change_set],
                           "counts": summary["counts"], "pending_total": summary["pending_total"],
                       })
    for pid, entries in audits.items():
        await audit_project(db, user_id=user_id, project_id=pid, domain=domain, action="sync_global",
                            source=source, changes=entries, publish_id=publish_id)
    events = [{"project_id": str(pid), "slot_keys": slots}
              for pid, slots in changed_slots(ctx.items, outcomes).items()]
    return {"publish_id": str(publish_id), "idempotent": False, "domain": domain, "scope": scope,
            "summary": summary, "versions": versions, "events": events}


async def list_publishes(db: AsyncSession, *, domain: str | None = None, scope: str | None = None,
                         status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    q = sa.select(FormulaPublish)
    if domain:
        q = q.where(FormulaPublish.domain == domain)
    if scope:
        q = q.where(FormulaPublish.scope == scope)
    if status:
        q = q.where(FormulaPublish.status == status)
    rows = (await db.execute(q.order_by(FormulaPublish.published_at.desc()).limit(max(1, min(limit, 200))))).scalars()
    return [publish_to_dict(r) for r in rows]


def publish_to_dict(r: FormulaPublish) -> dict[str, Any]:
    return {
        "id": str(r.id), "domain": r.domain, "scope": r.scope, "target": r.target, "source": r.source,
        "status": r.status, "template_id": str(r.template_id) if r.template_id else None,
        "source_project_id": str(r.source_project_id) if r.source_project_id else None,
        "change_set": r.change_set or [], "summary": r.summary or {}, "note": r.note,
        "published_by": str(r.published_by) if r.published_by else None,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "reviewed_by": str(r.reviewed_by) if r.reviewed_by else None,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
    }
