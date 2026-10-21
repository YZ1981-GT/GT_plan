"""一处修改，应用到全部（R7）：应用到指定项目（同级推送）、设为全局、全局候选审核。只 flush。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formula_setting_models import FormulaPublish
from app.services.formula_settings.audit import audit_global, audit_project, change_entry
from app.services.formula_settings.definitions import display_formula, get_spec
from app.services.formula_settings.effective import effective_slots, upstream_records
from app.services.formula_settings.engine import Decisions, lock_domain, lock_project
from app.services.formula_settings.errors import FormulaSettingError, NotFound
from app.services.formula_settings.pending import close_pending, upsert_pending
from app.services.formula_settings.project_ops import require_project
from app.services.formula_settings.projects import list_projects
from app.services.formula_settings.publish import preview_global, publish_global, publish_to_dict
from app.services.formula_settings.stores import get_store
from app.services.formula_settings.sync import (
    CATEGORY_LABELS,
    Action,
    Category,
    ConflictChoice,
    classify_push,
    decide_push,
)


def _plain(d: Mapping | None) -> dict | None:
    return None if d is None else {k: v for k, v in dict(d).items() if k != "_structure"}


async def _source_definitions(db: AsyncSession, domain: str, project_id: uuid.UUID,
                              slot_keys: list[str]) -> dict[str, dict]:
    """来源项目这些公式位的有效定义（含标签）。"""
    eff = await effective_slots(db, domain, project_id)
    out = {}
    for slot in dict.fromkeys(slot_keys):
        e = eff.get(slot)
        if e is None:
            raise FormulaSettingError(f"本项目没有公式位 {slot}")
        out[slot] = {"definition": e.definition, "label": e.label, "structure": e.structure}
    return out


# ── 应用到指定项目 ────────────────────────────────────────────────────────────


async def _push_plan(db: AsyncSession, domain: str, source_id: uuid.UUID, slot_keys: list[str],
                     target_ids: list[uuid.UUID]) -> tuple[dict[str, dict], list[dict[str, Any]]]:
    source = await _source_definitions(db, domain, source_id, slot_keys)
    targets = await list_projects(db, domain, ids=[t for t in target_ids if t != source_id])
    plan = []
    for t in targets:
        eff = await effective_slots(db, domain, t.id, scope=t.scope)
        for slot, src in source.items():
            e = eff.get(slot)
            lo = e.local if e is not None else None
            category = classify_push(domain, source=src["definition"],
                                     target_effective=e.definition if e is not None else None,
                                     local=lo.local_state() if lo else None, frozen=t.frozen)
            plan.append({"target": t, "slot_key": slot, "label": src["label"], "structure": src["structure"],
                         "source": src["definition"], "effective": e, "category": category})
    return source, plan


def _push_item_dict(domain: str, p: dict[str, Any]) -> dict[str, Any]:
    t, e = p["target"], p["effective"]
    lo = e.local if e is not None else None
    return {
        "key": f"{t.id}|{p['slot_key']}", "project_id": str(t.id), "project_name": t.name,
        "project_status": t.status, "frozen": t.frozen, "slot_key": p["slot_key"], "label": p["label"],
        "category": p["category"].value, "category_label": CATEGORY_LABELS.get(p["category"].value, ""),
        "new_upstream": _plain(p["source"]), "new_formula": display_formula(domain, p["source"]),
        "local_definition": _plain(e.definition) if e is not None else None,
        "local_formula": display_formula(domain, e.definition) if e is not None else "",
        "base_definition": _plain(lo.base_definition) if lo else None,
        "base_formula": display_formula(domain, lo.base_definition) if lo else "",
        "layer": e.layer if e is not None else "global",
    }


async def apply_preview(db: AsyncSession, *, domain: str, project_id: uuid.UUID, slot_keys: list[str],
                        target_ids: list[uuid.UUID]) -> dict[str, Any]:
    get_spec(domain)
    _, plan = await _push_plan(db, domain, project_id, slot_keys, target_ids)
    counts: dict[str, int] = {c.value: 0 for c in Category}
    for p in plan:
        counts[p["category"].value] += 1
    return {"domain": domain, "counts": counts, "conflict_count": counts[Category.CONFLICT.value],
            "items": [_push_item_dict(domain, p) for p in plan]}


async def apply_to_projects(db: AsyncSession, *, domain: str, project_id: uuid.UUID, slot_keys: list[str],
                            target_ids: list[uuid.UUID], decisions: Decisions, user_id: uuid.UUID | None,
                            request_id: str | None = None) -> dict[str, Any]:
    """把本项目这些公式位的有效定义写成目标项目的本项目适配（R7.3）。鉴权由路由逐目标校验。"""
    get_spec(domain)
    if request_id:
        replay = (await db.execute(sa.select(FormulaPublish).where(FormulaPublish.request_id == request_id))
                  ).scalars().first()
        if replay is not None:
            return {"publish_id": str(replay.id), "idempotent": True, "summary": replay.summary, "events": []}
    for t in sorted(set(target_ids) - {project_id}, key=str):
        await lock_project(db, domain, t)
    source, plan = await _push_plan(db, domain, project_id, slot_keys, target_ids)
    store = get_store(domain)
    publish_id = uuid.uuid4()
    counts: dict[str, int] = {c.value: 0 for c in Category}
    events: dict[uuid.UUID, list[str]] = {}
    audits: dict[uuid.UUID, list[dict[str, Any]]] = {}
    pending_total = 0
    upstream_cache: dict[str, dict] = {}
    for p in plan:
        t, slot, e = p["target"], p["slot_key"], p["effective"]
        counts[p["category"].value] += 1
        lo = e.local if e is not None else None
        if t.scope not in upstream_cache:
            upstream_cache[t.scope] = await upstream_records(db, store, t.scope)
        up = upstream_cache[t.scope].get(slot)
        choice = decisions.conflict_choices.get(f"{t.id}|{slot}", decisions.default_conflict)
        effect = decide_push(domain, p["category"], source=p["source"], local=lo.local_state() if lo else None,
                             upstream=up.definition if up else None, upstream_version=up.version if up else None,
                             conflict_choice=choice)
        before = e.definition if e is not None else None
        if effect.action is Action.SET_LOCAL:
            await store.write_project(
                db, t.id, slot, definition=dict(effect.local_definition or {}),
                base_definition=effect.base_definition, base_version=effect.base_version, pinned=False,
                base_origin=(lo.base_origin if lo is not None and lo.base_definition is not None else "global"),
                base_template_id=lo.base_template_id if lo is not None else None, user_id=user_id,
                label=p["label"], structure=p["structure"] or None)
            await close_pending(db, t.id, domain, [slot])
        elif effect.action is Action.DELETE_LOCAL:
            if lo is not None:
                await store.delete_project(db, t.id, slot)
            await close_pending(db, t.id, domain, [slot])
        elif effect.action is Action.PENDING:
            pending_total += 1
            await upsert_pending(db, project_id=t.id, domain=domain, slot_key=slot, slot_label=p["label"],
                                 reason="conflict", base_definition=lo.base_definition if lo else None,
                                 upstream_definition=p["source"], upstream_version=None,
                                 local_definition=before, publish_id=publish_id, upstream_origin="project")
        if effect.effective_changed and not t.frozen:
            events.setdefault(t.id, []).append(slot)
        if effect.action is not Action.NONE:
            after = effect.local_definition if effect.action is Action.SET_LOCAL else (
                up.definition if effect.action is Action.DELETE_LOCAL and up else before)
            audits.setdefault(t.id, []).append(change_entry(
                domain, slot, before, after, effect=("pending" if effect.action is Action.PENDING else "push"),
                category=p["category"].value, source_project_id=project_id,
                config_id=lo.row_id if lo is not None else None))
    summary = {"counts": counts, "pending_total": pending_total,
               "changed_projects": [str(pid) for pid in events], "target_count": len({p["target"].id for p in plan})}
    db.add(FormulaPublish(
        id=publish_id, domain=domain, scope="", target="projects", source="apply_to_projects",
        source_project_id=project_id, request_id=request_id, status="published",
        change_set=[{"slot_key": s, "label": v["label"], "new": _plain(v["definition"])} for s, v in source.items()],
        summary=summary, published_by=user_id,
    ))
    await db.flush()
    for pid, entries in audits.items():
        await audit_project(db, user_id=user_id, project_id=pid, domain=domain, action="push",
                            source="apply_to_projects", changes=entries, publish_id=publish_id)
    return {"publish_id": str(publish_id), "idempotent": False, "summary": summary,
            "events": [{"project_id": str(pid), "slot_keys": slots} for pid, slots in events.items()]}


# ── 设为全局 / 全局候选 ───────────────────────────────────────────────────────


async def _promote_changes(db: AsyncSession, domain: str, project_id: uuid.UUID,
                           slot_keys: list[str]) -> tuple[str, list[dict[str, Any]]]:
    project = await require_project(db, domain, project_id, writable=False)
    store = get_store(domain)
    source = await _source_definitions(db, domain, project_id, slot_keys)
    current = await store.list_global_exact(db, project.scope)
    changes = []
    for slot, src in source.items():
        rec = current.get(slot)
        changes.append({"slot_key": slot, "definition": _plain(src["definition"]),
                        "expected_version": rec.version if rec else None, "label": src["label"],
                        "structure": src["structure"] or None})
    return project.scope, changes


async def promote_preview(db: AsyncSession, *, domain: str, project_id: uuid.UUID,
                          slot_keys: list[str]) -> dict[str, Any]:
    scope, changes = await _promote_changes(db, domain, project_id, slot_keys)
    return await preview_global(db, domain=domain, scope=scope, changes=changes)


async def promote(db: AsyncSession, *, domain: str, project_id: uuid.UUID, slot_keys: list[str],
                  is_admin: bool, user_id: uuid.UUID | None, decisions: Decisions | None = None,
                  request_id: str | None = None, note: str | None = None) -> dict[str, Any]:
    """admin：直接作为全局发布（source=promote）；其他人：提交全局候选，等待 admin 审核。"""
    scope, changes = await _promote_changes(db, domain, project_id, slot_keys)
    if is_admin:
        return await publish_global(db, domain=domain, scope=scope, changes=changes, user_id=user_id,
                                    decisions=decisions, request_id=request_id, source="promote",
                                    source_project_id=project_id, note=note)
    await lock_domain(db, domain, shared=True)
    if request_id:
        replay = (await db.execute(sa.select(FormulaPublish).where(FormulaPublish.request_id == request_id))
                  ).scalars().first()
        if replay is not None:
            return {"candidate": publish_to_dict(replay), "idempotent": True, "events": []}
    current = await get_store(domain).list_global_exact(db, scope)
    row = FormulaPublish(
        domain=domain, scope=scope, target="global", source="candidate", source_project_id=project_id,
        request_id=request_id, status="pending", published_by=user_id, note=note,
        change_set=[{**c, "old": _plain(current[c["slot_key"]].definition) if c["slot_key"] in current else None,
                     "new": c["definition"], "old_version": c["expected_version"]} for c in changes],
        summary={},
    )
    db.add(row)
    await db.flush()
    await audit_global(db, user_id=user_id, domain=domain, scope=scope, action="formula.candidate_submitted",
                       resource_id=row.id, details={"source": "candidate", "candidate_id": str(row.id),
                                                    "slot_keys": [c["slot_key"] for c in changes], "note": note or ""})
    return {"candidate": publish_to_dict(row), "idempotent": False, "events": []}


async def _candidate(db: AsyncSession, publish_id: uuid.UUID) -> FormulaPublish:
    row = await db.get(FormulaPublish, publish_id)
    if row is None or row.status != "pending":
        raise NotFound("全局候选不存在或已处理")
    return row


async def _candidate_changes(db: AsyncSession, row: FormulaPublish) -> list[dict[str, Any]]:
    current = await get_store(row.domain).list_global_exact(db, row.scope)
    return [{"slot_key": c["slot_key"], "definition": c.get("new"), "label": c.get("label") or "",
             "structure": c.get("structure"),
             "expected_version": current[c["slot_key"]].version if c["slot_key"] in current else None}
            for c in (row.change_set or [])]


async def candidate_preview(db: AsyncSession, publish_id: uuid.UUID) -> dict[str, Any]:
    row = await _candidate(db, publish_id)
    if row.domain == "preset":  # 自定义公式预设候选：不涉及项目同步，只列新旧
        return {"domain": row.domain, "scope": "", "changes": row.change_set or [], "items": [],
                "summary": {}, "candidate": publish_to_dict(row), "global_changed_since_submit": []}
    changes = await _candidate_changes(db, row)
    preview = await preview_global(db, domain=row.domain, scope=row.scope, changes=changes)
    stale = [c["slot_key"] for c in (row.change_set or []) if c.get("old_version") != next(
        (x["expected_version"] for x in changes if x["slot_key"] == c["slot_key"]), None)]
    return {**preview, "candidate": publish_to_dict(row), "global_changed_since_submit": stale}


async def review_candidate(db: AsyncSession, *, publish_id: uuid.UUID, approve: bool, user_id: uuid.UUID | None,
                           decisions: Decisions | None = None, note: str | None = None) -> dict[str, Any]:
    row = await _candidate(db, publish_id)
    row.reviewed_by, row.reviewed_at = user_id, datetime.now(timezone.utc)
    if not approve:
        row.status = "rejected"
        row.note = "\n".join(x for x in (row.note, f"驳回：{note}" if note else "") if x)
        await db.flush()
        await audit_global(db, user_id=user_id, domain=row.domain, scope=row.scope,
                           action="formula.candidate_rejected", resource_id=row.id,
                           details={"source": "candidate", "candidate_id": str(row.id), "note": note or ""})
        return {"candidate": publish_to_dict(row), "events": []}
    if row.domain == "preset":
        from app.services.formula_settings import custom_presets

        stats = await custom_presets.approve_candidate(db, row, user_id=user_id)
        row.status, row.summary = "published", stats
        await db.flush()
        return {"candidate": publish_to_dict(row), "events": [], "custom_presets_changed": True}
    result = await publish_global(db, domain=row.domain, scope=row.scope, changes=await _candidate_changes(db, row),
                                  user_id=user_id, decisions=decisions, source="candidate",
                                  source_project_id=row.source_project_id, note=note or row.note)
    row.status = "published"
    row.summary = {"publish_id": result["publish_id"], **(result.get("summary") or {})}
    await db.flush()
    return {**result, "candidate": publish_to_dict(row)}
