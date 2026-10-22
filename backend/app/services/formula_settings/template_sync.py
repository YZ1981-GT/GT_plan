"""公式模板与项目的同步：订阅、发布新版本、退订（R13.3~R13.5，design §16.2）。只 flush，路由 commit。

四个动作都是「上游从 U0 变为 U1」，直接复用同步内核（:mod:`engine`）：

* 订阅：U0 = 全局（或系统预设），U1 = 模板，只对模板定义的公式位；模板定义物化为本项目层行
  （``base_origin='template'``）。冲突逐条「采用模板 / 保留本项目」，未决的进待确认。
* 发布新版本：U0 = 旧版本，U1 = 新版本，范围 = 订阅者；与全局发布同一套预览、项目「应用 / 暂缓」、
  冲突决策与待确认。暂缓的订阅固定在旧版本（读该版本快照）。模板删掉的公式位回到全局。
* 退订：「保留模板公式」= 把模板定义改记为本项目适配（基线 = 全局，不判冲突）；「回到全局」=
  U0 = 模板、U1 = 全局，没改过的自动回到全局，改过且与全局不同的逐条确认。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formula_setting_models import (
    FormulaPublish,
    FormulaSetting,
    FormulaSyncItem,
    FormulaTemplate,
    FormulaTemplateSubscription,
    FormulaTemplateVersion,
)
from app.services.formula_settings.audit import audit_global, audit_project, change_entry
from app.services.formula_settings.definitions import exec_hash, get_spec, normalize, same_exec
from app.services.formula_settings.domain_stores import validate_definition
from app.services.formula_settings.effective import upstream_records
from app.services.formula_settings.engine import (
    ApplyOutcome,
    Decisions,
    PlanItem,
    apply_effect,
    changed_slots,
    decide_item,
    lock_project,
    summarize,
)
from app.services.formula_settings.errors import FormulaSettingError, NotFound, VersionConflict, VersionRequired
from app.services.formula_settings.project_ops import require_project
from app.services.formula_settings.projects import ProjectInfo, get_project
from app.services.formula_settings.stores import SlotRecord, get_store
from app.services.formula_settings.sync import ProjectChoice
from app.services.formula_settings.template_service import global_scope
from app.services.formula_settings.templates import active_subscription, subscribed_definitions, template_rows


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _origin(rec: SlotRecord | None) -> str:
    return "preset" if rec is not None and rec.layer == "preset" else "global"


async def _audit_subscription(db: AsyncSession, *, user_id: uuid.UUID | None, project_id: uuid.UUID, domain: str,
                              template_id: uuid.UUID, action: str, details: dict[str, Any]) -> None:
    """订阅 / 退订本身留一条（带 project_id）；逐公式位的变化另由 ``audit_project`` 记。"""
    from app.services.audit_log_helper import append_audit_log

    await append_audit_log(db, {
        "user_id": user_id, "project_id": project_id, "action": f"formula.template_{action}",
        "resource_type": "formula_template", "resource_id": str(template_id),
        "details": {"domain": domain, "template_id": str(template_id), **details},
    })


async def _lock_template(db: AsyncSession, template_id: uuid.UUID) -> None:
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        await db.execute(sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                         {"k": f"formula_template:{template_id}"})


def _result(domain_items: dict[str, list[PlanItem]], projects: list[ProjectInfo],
            outcomes: Mapping[str, ApplyOutcome] | None = None) -> dict[str, Any]:
    items = [it for its in domain_items.values() for it in its]
    return {"summary": summarize(items, projects, outcomes),
            "items": [{**it.to_dict(d), "domain": d} for d, its in domain_items.items() for it in its
                      if not (it.category and it.category.value == "inherit" and not it.materialize)]}


async def _apply(db: AsyncSession, domain_items: dict[str, list[PlanItem]], decisions: Decisions, *,
                 publish_id: uuid.UUID | None, user_id: uuid.UUID | None, action: str,
                 source: str) -> tuple[dict[str, ApplyOutcome], list[dict[str, Any]]]:
    outcomes: dict[str, ApplyOutcome] = {}
    events: list[dict[str, Any]] = []
    for domain, items in domain_items.items():
        store = get_store(domain)
        audits: dict[uuid.UUID, list[dict]] = {}
        for it in items:
            out = await apply_effect(db, store, it, decide_item(domain, it, decisions), publish_id=publish_id,
                                     user_id=user_id)
            outcomes[it.key] = out
            if out.audit is not None:
                audits.setdefault(it.project.id, []).append(out.audit)
        for pid, entries in audits.items():
            await audit_project(db, user_id=user_id, project_id=pid, domain=domain, action=action, source=source,
                                changes=entries, publish_id=publish_id)
        events += [{"project_id": str(pid), "domain": domain, "slot_keys": slots}
                   for pid, slots in changed_slots(items, {k: outcomes[k] for k in (i.key for i in items)}).items()]
    return outcomes, events


# ── 订阅 ──────────────────────────────────────────────────────────────────────


async def _subscribe_plan(db: AsyncSession, project_id: uuid.UUID, tpl: FormulaTemplate,
                          domain: str) -> tuple[ProjectInfo, list[PlanItem]]:
    if tpl.is_deleted or tpl.status != "active":
        raise NotFound("公式模板不存在或已停用")
    if domain not in (tpl.domains or []):
        raise FormulaSettingError(f"该模板没有{get_spec(domain).label}")
    project = await require_project(db, domain, project_id)
    want = global_scope(domain, tpl.applicable_scope)
    if tpl.applicable_scope and want is not None and want != project.scope:
        raise FormulaSettingError(f"模板适用于 {want}，本项目是 {project.scope}，不能订阅")
    sub = await active_subscription(db, project_id, domain)
    if sub is not None:
        raise FormulaSettingError("本项目已订阅该模板" if sub.template_id == tpl.id
                                  else "本项目已订阅其他模板，请先退订", status_code=409)
    store = get_store(domain)
    upstream = await upstream_records(db, store, project.scope)
    local = await store.list_project(db, project_id)
    items = []
    for slot, row in sorted((await template_rows(db, tpl.id, domain)).items()):
        up, lo = upstream.get(slot), local.get(slot)
        item = PlanItem(project=project, slot_key=slot, label=row.slot_label or slot,
                        old_up=up.definition if up else None, old_version=up.version if up else None,
                        old_origin=_origin(up), new_up=dict(row.definition or {}), new_version=tpl.version,
                        new_origin="template", local=lo, structure=dict((row.definition or {}).get("_structure")
                                                                        or {}),
                        new_template_id=tpl.id, materialize=True)
        item.classify(domain)
        items.append(item)
    return project, items


async def subscribe_preview(db: AsyncSession, *, project_id: uuid.UUID, tpl: FormulaTemplate,
                            domain: str) -> dict[str, Any]:
    project, items = await _subscribe_plan(db, project_id, tpl, domain)
    return {"template_id": str(tpl.id), "template_version": tpl.version, "domain": domain,
            **_result({domain: items}, [project])}


async def subscribe(db: AsyncSession, *, project_id: uuid.UUID, tpl: FormulaTemplate, domain: str,
                    decisions: Decisions | None, user_id: uuid.UUID | None) -> dict[str, Any]:
    await lock_project(db, domain, project_id)
    project, items = await _subscribe_plan(db, project_id, tpl, domain)
    outcomes, events = await _apply(db, {domain: items}, _project_decisions(decisions), publish_id=None,
                                    user_id=user_id, action="template_subscribe", source="template_subscribe")
    # 冲突交本项目确认的公式位：本项目行改记为模板层（基线不动），此后全局发布跳过它，待确认仍以模板为上游
    store = get_store(domain)
    for it in items:
        lo = it.local
        if outcomes[it.key].pending and lo is not None and lo.base_origin != "template":
            await store.write_project(db, project_id, it.slot_key, definition=dict(lo.definition or {}),
                                      base_definition=lo.base_definition, base_version=lo.base_version,
                                      pinned=lo.pinned, base_origin="template", base_template_id=tpl.id,
                                      user_id=user_id, label=lo.label)
    db.add(FormulaTemplateSubscription(id=uuid.uuid4(), project_id=project_id, domain=domain, template_id=tpl.id,
                                       template_version=tpl.version, pinned=False, is_active=True,
                                       subscribed_by=user_id, subscribed_at=_now()))
    await db.flush()
    result = {"template_id": str(tpl.id), "template_version": tpl.version, "domain": domain,
              **_result({domain: items}, [project], outcomes)}
    await _audit_subscription(db, user_id=user_id, project_id=project_id, domain=domain, template_id=tpl.id,
                              action="subscribed", details={"version": tpl.version,
                                                            "counts": result["summary"]["counts"]})
    return {**result, "events": events}


def _project_decisions(decisions: Decisions | None) -> Decisions:
    """订阅 / 退订是项目自己的动作：没有「暂缓」，只有逐条冲突决策。"""
    d = decisions or Decisions()
    return Decisions(conflict_choices=dict(d.conflict_choices), default_conflict=d.default_conflict)


# ── 退订 ──────────────────────────────────────────────────────────────────────


async def _unsubscribe_plan(db: AsyncSession, project_id: uuid.UUID, domain: str):
    sub = await active_subscription(db, project_id, domain)
    if sub is None:
        raise NotFound("本项目没有订阅该域的公式模板")
    project = await require_project(db, domain, project_id)
    store = get_store(domain)
    upstream = await upstream_records(db, store, project.scope)
    local = await store.list_project(db, project_id)
    tdefs, tver = await subscribed_definitions(db, sub)
    rows = {s: lo for s, lo in local.items() if lo.base_origin == "template" and lo.base_template_id == sub.template_id}
    items = []
    for slot, lo in sorted(rows.items()):
        up = upstream.get(slot)
        item = PlanItem(project=project, slot_key=slot, label=lo.label or slot,
                        old_up=tdefs.get(slot, lo.base_definition), old_version=tver, old_origin="template",
                        new_up=up.definition if up else None, new_version=up.version if up else None,
                        new_origin=_origin(up), local=lo, structure=dict(lo.structure or {}),
                        old_template_id=sub.template_id, retire_same=True)
        item.classify(domain)
        items.append(item)
    return sub, project, store, upstream, rows, items


async def unsubscribe_preview(db: AsyncSession, *, project_id: uuid.UUID, domain: str,
                              mode: str) -> dict[str, Any]:
    sub, project, _, _, _, items = await _unsubscribe_plan(db, project_id, domain)
    if mode == "keep":
        return {"template_id": str(sub.template_id), "domain": domain, "mode": mode,
                "summary": summarize([], [project]), "items": [], "kept": len(items)}
    return {"template_id": str(sub.template_id), "domain": domain, "mode": mode, **_result({domain: items}, [project])}


async def unsubscribe(db: AsyncSession, *, project_id: uuid.UUID, domain: str, mode: str,
                      decisions: Decisions | None, user_id: uuid.UUID | None) -> dict[str, Any]:
    if mode not in ("keep", "global"):
        raise FormulaSettingError("退订方式须为 keep（保留模板公式）或 global（回到全局）")
    await lock_project(db, domain, project_id)
    sub, project, store, upstream, rows, items = await _unsubscribe_plan(db, project_id, domain)
    # 模板来的待确认事项不再有上游：结案（被替代）
    await db.execute(sa.update(FormulaSyncItem).where(
        FormulaSyncItem.project_id == project_id, FormulaSyncItem.domain == domain,
        FormulaSyncItem.status == "pending", FormulaSyncItem.upstream_template_id == sub.template_id,
    ).values(status="superseded", updated_at=_now()).execution_options(synchronize_session=False))
    events: list[dict[str, Any]] = []
    outcomes: dict[str, ApplyOutcome] = {}
    if mode == "global":
        outcomes, events = await _apply(db, {domain: items}, _project_decisions(decisions), publish_id=None,
                                        user_id=user_id, action="template_unsubscribe", source="template_unsubscribe")
    # 余下仍标着「来自模板」的行改记为本项目适配（基线 = 全局）：此后全局发布正常同步，不再被当成模板层跳过
    audits = []
    for slot, lo in sorted((await store.list_project(db, project_id)).items()):
        if lo.base_origin != "template" or lo.base_template_id != sub.template_id:
            continue
        up = upstream.get(slot)
        if mode == "keep" and up is not None and same_exec(domain, lo.definition, up.definition):
            await store.delete_project(db, project_id, slot)  # 与全局相同：回到继承
            continue
        keep_base = mode == "global"  # 回到全局时冲突未决：基线保留模板定义，待确认事项按「基线 → 全局」比
        await store.write_project(
            db, project_id, slot, definition=dict(lo.definition or {}),
            base_definition=lo.base_definition if keep_base else (up.definition if up else None),
            base_version=lo.base_version if keep_base else (up.version if up else None),
            pinned=lo.pinned if keep_base else False, base_origin=_origin(up), base_template_id=None,
            user_id=user_id, label=lo.label)
        if mode == "keep":
            audits.append(change_entry(domain, slot, lo.definition, lo.definition, effect="template_keep"))
    if audits:
        await audit_project(db, user_id=user_id, project_id=project_id, domain=domain, action="template_unsubscribe",
                            source="template_unsubscribe", changes=audits)
    sub.is_active, sub.unsubscribed_at = False, _now()
    await db.flush()
    await _audit_subscription(db, user_id=user_id, project_id=project_id, domain=domain,
                              template_id=sub.template_id, action="unsubscribed",
                              details={"mode": mode, "slot_count": len(rows)})
    return {"template_id": str(sub.template_id), "domain": domain, "mode": mode,
            **(_result({domain: items}, [project], outcomes) if mode == "global" else
               {"summary": summarize([], [project]), "items": []}), "events": events}


# ── 发布新版本 ────────────────────────────────────────────────────────────────


def _parse_changes(tpl: FormulaTemplate, raw: list[Mapping[str, Any]]) -> dict[str, dict[str, dict | None]]:
    out: dict[str, dict[str, dict | None]] = {}
    for c in raw:
        domain, slot = str(c.get("domain") or ""), str(c.get("slot_key") or "").strip()
        get_spec(domain)
        if not slot:
            raise FormulaSettingError("公式位不能为空")
        d = c.get("definition")
        if d is not None and not isinstance(d, Mapping):
            raise FormulaSettingError(f"公式位 {slot} 的定义格式不正确")
        if slot in out.get(domain, {}):
            raise FormulaSettingError(f"公式位重复：{slot}")
        out.setdefault(domain, {})[slot] = dict(d) if d is not None else None
    return out


async def _publish_plan(db: AsyncSession, tpl: FormulaTemplate, raw: list[Mapping[str, Any]]):
    changes = _parse_changes(tpl, raw)
    current = {d: await template_rows(db, tpl.id, d) for d in changes}
    effective: dict[str, dict[str, dict | None]] = {}
    for domain, slots in changes.items():
        for slot, d in slots.items():
            row = current[domain].get(slot)
            if d is not None:
                merged = {**(dict(row.definition or {}) if row else {}), **d}
                validate_definition(domain, merged, f"{get_spec(domain).label} {slot}", slot)
                if row is not None and normalize(domain, merged) == normalize(domain, row.definition) \
                        and merged.get("_structure") == (row.definition or {}).get("_structure"):
                    continue
                effective.setdefault(domain, {})[slot] = merged
            elif row is not None:
                effective.setdefault(domain, {})[slot] = None
    subs = (await db.execute(sa.select(FormulaTemplateSubscription).where(
        FormulaTemplateSubscription.template_id == tpl.id, FormulaTemplateSubscription.is_active == sa.true(),
        FormulaTemplateSubscription.domain.in_(list(effective) or [""])))).scalars().all()
    domain_items: dict[str, list[PlanItem]] = {}
    projects: dict[uuid.UUID, ProjectInfo] = {}
    for sub in subs:
        project = await get_project(db, sub.domain, sub.project_id)
        if project is None:
            continue
        projects[project.id] = project
        store = get_store(sub.domain)
        upstream = await upstream_records(db, store, project.scope)
        local = await store.list_project(db, sub.project_id)
        old_defs, old_ver = await subscribed_definitions(db, sub)
        for slot, new in sorted(effective[sub.domain].items()):
            up, lo, old_t = upstream.get(slot), local.get(slot), old_defs.get(slot)
            row = current[sub.domain].get(slot)
            label = (row.slot_label if row else None) or slot
            item = PlanItem(
                project=project, slot_key=slot, label=label,
                old_up=old_t if old_t is not None else (up.definition if up else None),
                old_version=old_ver if old_t is not None else (up.version if up else None),
                old_origin="template" if old_t is not None else _origin(up),
                new_up=new if new is not None else (up.definition if up else None),
                new_version=tpl.version + 1 if new is not None else (up.version if up else None),
                new_origin="template" if new is not None else _origin(up), local=lo,
                structure=dict((new or {}).get("_structure") or (lo.structure if lo else {}) or {}),
                old_template_id=tpl.id if old_t is not None else None,
                new_template_id=tpl.id if new is not None else None,
                materialize=new is not None, retire_same=new is None)
            item.classify(sub.domain)
            domain_items.setdefault(sub.domain, []).append(item)
    return effective, current, list(subs), list(projects.values()), domain_items


def _check_version(tpl: FormulaTemplate, expected_version: int | None) -> None:
    if expected_version is None:
        raise VersionRequired("发布模板新版本必须带当前版本号，请刷新后重试")
    if int(expected_version) != tpl.version:
        raise VersionConflict("模板已被他人修改，请刷新后重试",
                              detail={"expected_version": expected_version, "current_version": tpl.version})


async def publish_preview(db: AsyncSession, tpl: FormulaTemplate, *, changes: list[Mapping[str, Any]],
                          expected_version: int | None) -> dict[str, Any]:
    _check_version(tpl, expected_version)
    effective, current, _, projects, domain_items = await _publish_plan(db, tpl, changes)
    return {"template_id": str(tpl.id), "version": tpl.version, "next_version": tpl.version + 1,
            "changes": _change_rows(effective, current), **_result(domain_items, projects)}


def _change_rows(effective, current) -> list[dict[str, Any]]:
    return [{"domain": d, "slot_key": s, "label": (current[d].get(s).slot_label if current[d].get(s) else None) or s,
             "old": (current[d][s].definition if s in current[d] else None), "new": new, "deleted": new is None}
            for d, slots in effective.items() for s, new in sorted(slots.items())]


async def publish_template(db: AsyncSession, tpl: FormulaTemplate, *, changes: list[Mapping[str, Any]],
                           expected_version: int | None, user_id: uuid.UUID | None,
                           decisions: Decisions | None = None, request_id: str | None = None,
                           note: str | None = None) -> dict[str, Any]:
    await _lock_template(db, tpl.id)
    if request_id:
        replay = (await db.execute(sa.select(FormulaPublish).where(FormulaPublish.request_id == request_id))
                  ).scalars().first()
        if replay is not None:
            return {"publish_id": str(replay.id), "idempotent": True, "summary": replay.summary, "events": []}
    await db.refresh(tpl)
    _check_version(tpl, expected_version)
    effective, current, subs, projects, domain_items = await _publish_plan(db, tpl, changes)
    if not effective:
        raise FormulaSettingError("模板没有任何改动")
    decisions = decisions or Decisions()
    for pid in sorted({it.project.id for its in domain_items.values() for it in its}, key=str):
        for d in domain_items:
            await lock_project(db, d, pid)
    new_version, publish_id = tpl.version + 1, uuid.uuid4()
    rows = await _write_rows(db, tpl, effective, current, user_id)
    change_rows = _change_rows(effective, current)
    outcomes, events = await _apply(db, domain_items, decisions, publish_id=publish_id, user_id=user_id,
                                    action="template_sync", source="template_publish")
    tpl.version, tpl.updated_by, tpl.updated_at = new_version, user_id, _now()
    db.add(FormulaTemplateVersion(id=uuid.uuid4(), template_id=tpl.id, version=new_version, note=note,
                                  published_by=user_id, change_set=change_rows,
                                  snapshot={d: {s: dict(r.definition or {}) for s, r in slots.items()}
                                            for d, slots in rows.items()}))
    for sub in subs:
        frozen = any(p.id == sub.project_id and p.frozen for p in projects)
        if decisions.project(sub.project_id) is ProjectChoice.DEFER:
            sub.pinned = True  # 暂缓：固定在旧版本（读旧版本快照）
        elif not frozen:
            sub.template_version, sub.pinned = new_version, False
    summary = _result(domain_items, projects, outcomes)["summary"]
    record_domain = next(iter(effective)) if len(effective) == 1 else "template"  # 列 32 字符：多域记 template
    db.add(FormulaPublish(id=publish_id, domain=record_domain, scope=tpl.applicable_scope or "",
                          target="template", template_id=tpl.id, source="template_publish", request_id=request_id,
                          status="published", change_set=change_rows, summary=summary, note=note,
                          published_by=user_id))
    await db.flush()
    await audit_global(db, user_id=user_id, domain=",".join(sorted(effective)), scope=tpl.applicable_scope or "",
                       action="formula.template_published", resource_id=tpl.id, details={
                           "template_id": str(tpl.id), "version": new_version, "publish_id": str(publish_id),
                           "changes": [change_entry(c["domain"], c["slot_key"], c["old"], c["new"])
                                       for c in change_rows], "counts": summary["counts"]})
    return {"publish_id": str(publish_id), "idempotent": False, "template_id": str(tpl.id), "version": new_version,
            "summary": summary, "events": events}


async def _write_rows(db: AsyncSession, tpl: FormulaTemplate, effective, current,
                      user_id: uuid.UUID | None) -> dict[str, dict[str, FormulaSetting]]:
    """写模板行（新版本）；返回新版本全部定义（快照用）。基线记为当前全局（之后全局再变才提示）。"""
    for domain, slots in effective.items():
        scope = global_scope(domain, tpl.applicable_scope)
        glob = await get_store(domain).list_global(db, scope) if scope else {}
        for slot, new in slots.items():
            row = current[domain].get(slot)
            if new is None:
                row.is_deleted, row.version, row.updated_by, row.updated_at = True, row.version + 1, user_id, _now()
                continue
            if row is None:
                row = FormulaSetting(id=uuid.uuid4(), domain=domain, layer="template", scope="", template_id=tpl.id,
                                     slot_key=slot, slot_label=slot, version=0, created_by=user_id)
                db.add(row)
            row.definition, row.definition_hash = dict(new), exec_hash(domain, new)
            row.version, row.updated_by, row.updated_at = (row.version or 0) + 1, user_id, _now()
            g = glob.get(slot)
            row.base_definition = {k: v for k, v in g.definition.items() if k != "_structure"} if g else None
            row.base_version, row.base_origin = (g.version, "global") if g else (None, None)
    await db.flush()
    domains = sorted(set(tpl.domains or []) | set(effective))
    tpl.domains = domains
    return {d: await template_rows(db, tpl.id, d) for d in domains}


async def refresh_subscription(db: AsyncSession, project_id: uuid.UUID, domain: str,
                               template_id: uuid.UUID | None) -> None:
    """暂缓的订阅处理完全部模板待确认后跟上模板当前版本（处理待确认时调用）。"""
    if template_id is None:
        return
    sub = await active_subscription(db, project_id, domain)
    if sub is None or sub.template_id != template_id or not sub.pinned:
        return
    left = await db.scalar(sa.select(sa.func.count()).select_from(FormulaSyncItem).where(
        FormulaSyncItem.project_id == project_id, FormulaSyncItem.domain == domain,
        FormulaSyncItem.status == "pending", FormulaSyncItem.upstream_template_id == template_id))
    if not left:
        tpl = await db.get(FormulaTemplate, template_id)
        sub.pinned, sub.template_version = False, tpl.version if tpl else sub.template_version
