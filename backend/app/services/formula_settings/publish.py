"""全局设置：影响预览与发布（R2 / R3 / R4，design §6）。只 flush，路由 commit。

发布步骤：域排他锁 → 请求号幂等 → 逐公式位 CAS（缺版本 428、不一致 409，整批不写）→
对使用该作用范围的项目逐（项目, 公式位）分类 → 写全局（版本 +1）→ 按决策写各项目 →
待确认事项 → 发布记录 → 审计（全局一条 + 每项目）。

发布记录列表 :func:`list_publishes` 按查看人过滤与裁剪（spec formula-hub-integrity-closure 需求 7.4，ADR-FHIC-20）。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formula_setting_models import FormulaPublish, FormulaTemplate
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
from app.services.formula_settings.template_access import Viewer
from app.services.report_freshness import mark_changed, slot_row_codes

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
                domain=domain, project=p, slot_key=slot,
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
                item.classify()
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
        "items": [it.to_dict() for it in ctx.items if not (it.category and it.category.value == "inherit")],
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
    outcomes: dict[str, ApplyOutcome] = {}  # 键 = 决策键（带域，需求 8.4）
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
    changed = changed_slots(ctx.items, outcomes)
    if domain == "report" and changed:  # 同一事务内把有效定义变化的报表行及其闭包标过期（ADR-FHIC-04）
        await mark_changed(db, {pid: slot_row_codes(slots) for pid, slots in changed.items()})
    events = [{"project_id": str(pid), "slot_keys": slots} for pid, slots in changed.items()]
    return {"publish_id": str(publish_id), "idempotent": False, "domain": domain, "scope": scope,
            "summary": summary, "versions": versions, "events": events}


#: 全局候选的状态（审核前 / 被驳回）；``published`` 是已发布全局记录
_CANDIDATE_STATUSES = ("pending", "rejected")


def _visible_sql(viewer: Viewer) -> sa.ColumnElement[bool]:
    """规则 ①~③ 的 SQL 条件；④ 只取出模板记录，逐条按模板可见性判定（ADR-FHIC-20）。"""
    fp = FormulaPublish
    members = sorted(viewer.member_projects, key=str)
    member_ids = sa.bindparam("viewer_member_ids", members, type_=postgresql.ARRAY(postgresql.UUID(as_uuid=True)))
    member_text = sa.bindparam("viewer_member_text", [str(p) for p in members], type_=postgresql.ARRAY(sa.Text))
    in_member = fp.source_project_id == sa.any_(member_ids)
    return sa.or_(
        sa.and_(fp.target == "global", fp.status == "published"),
        sa.and_(fp.target == "global", fp.status.in_(_CANDIDATE_STATUSES),
                sa.or_(fp.published_by == viewer.user.id, in_member)),
        sa.and_(fp.target == "projects", sa.or_(in_member, fp.summary["changed_projects"].has_any(member_text))),
        fp.target == "template",
    )


def _visible_by_rule(viewer: Viewer, r: FormulaPublish) -> bool | None:
    """规则 ①~③ 的 Python 判定（与 :func:`_visible_sql` 同义，SQLite 用）；模板记录返回 None（交 ④）。"""
    if r.target == "template":
        return None
    member = viewer.member_projects
    if r.target == "global":
        if r.status == "published":
            return True
        return r.status in _CANDIDATE_STATUSES and (r.published_by == viewer.user.id or r.source_project_id in member)
    if r.target == "projects":
        changed = r.summary.get("changed_projects") if isinstance(r.summary, Mapping) else None
        touched = {str(p) for p in changed} if isinstance(changed, list) else set()
        return r.source_project_id in member or bool(touched & {str(p) for p in member})
    return False


async def _template_visible(db: AsyncSession, viewer: Viewer, template_id: uuid.UUID | None,
                            cache: dict[uuid.UUID, bool]) -> bool:
    """④ 模板记录按模板可见性（``Viewer.can_view``）；模板不存在 ⇒ 不可见。"""
    if template_id is None:
        return False
    if template_id not in cache:
        tpl = await db.get(FormulaTemplate, template_id)
        cache[template_id] = tpl is not None and await viewer.can_view(db, tpl)
    return cache[template_id]


def _redact(item: dict[str, Any], member_text: set[str]) -> dict[str, Any]:
    """裁掉他项目信息：本人不是成员的来源项目，以及 ``summary.projects`` / ``changed_projects`` 中的他项目条目。

    ``change_set`` 各写入方的条目只有公式位与定义（不带项目字段），无可裁条目。
    """
    if item["source_project_id"] not in member_text:
        item["source_project_id"] = None
    summary = dict(item["summary"]) if isinstance(item["summary"], Mapping) else {}
    if isinstance(summary.get("changed_projects"), list):
        summary["changed_projects"] = [p for p in summary["changed_projects"] if str(p) in member_text]
    if isinstance(summary.get("projects"), list):
        summary["projects"] = [p for p in summary["projects"]
                               if isinstance(p, Mapping) and str(p.get("project_id")) in member_text]
    item["summary"] = summary
    return item


async def list_publishes(db: AsyncSession, *, viewer: Viewer, domain: str | None = None, scope: str | None = None,
                         status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """发布记录，按 (published_at, id) 倒序；非 admin 只返回可见记录并裁掉他项目信息（需求 7.4，ADR-FHIC-20）。

    非 admin 可见：①已发布的全局记录；②全局候选（待审核 / 已驳回）—— 提交人本人，或本人是来源项目成员；
    ③项目间应用 —— 本人是来源项目成员，或 ``summary.changed_projects`` 含本人项目；④模板记录 —— 按模板可见性。
    PostgreSQL 把 ①~③ 下推为 SQL 条件，④ 逐条判定；SQLite（单测）四条都在 Python 判定。过滤后不足 ``limit`` 条时，
    以本批最后一条的 (published_at, id) 为游标取下一批（每批 ``limit`` 条），直到满 ``limit`` 或没有更多 ——
    最近 ``limit`` 条都不可见时第一页仍是其后的可见记录。
    """
    limit = max(1, min(limit, 200))
    base = sa.select(FormulaPublish)
    if domain:
        base = base.where(FormulaPublish.domain == domain)
    if scope:
        base = base.where(FormulaPublish.scope == scope)
    if status:
        base = base.where(FormulaPublish.status == status)
    order = (FormulaPublish.published_at.desc(), FormulaPublish.id.desc())
    if viewer.admin:
        return [publish_to_dict(r) for r in (await db.execute(base.order_by(*order).limit(limit))).scalars()]
    sql_rules = db.get_bind().dialect.name == "postgresql"
    if sql_rules:
        base = base.where(_visible_sql(viewer))
    member_text = {str(p) for p in viewer.member_projects}
    templates: dict[uuid.UUID, bool] = {}
    out: list[dict[str, Any]] = []
    cursor: tuple[Any, uuid.UUID] | None = None
    while len(out) < limit:
        q = base
        if cursor is not None:
            at, last_id = cursor
            q = q.where(sa.or_(FormulaPublish.published_at < at,
                               sa.and_(FormulaPublish.published_at == at, FormulaPublish.id < last_id)))
        batch = list((await db.execute(q.order_by(*order).limit(limit))).scalars())
        for r in batch:
            verdict = True if sql_rules and r.target != "template" else _visible_by_rule(viewer, r)
            if verdict is None:
                verdict = await _template_visible(db, viewer, r.template_id, templates)
            if verdict:
                out.append(_redact(publish_to_dict(r), member_text))
                if len(out) == limit:
                    break
        if len(batch) < limit:
            break
        cursor = (batch[-1].published_at, batch[-1].id)
    return out


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
