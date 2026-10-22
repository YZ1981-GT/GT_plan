"""公式模板：保存、改名与共享范围、删除、详情 / 版本 / 订阅者、与全局不一致提示、设为全局 / 全局候选
（R13.1 / R13.6~R13.9，design §16）。只 flush，路由 commit。

模板行存 ``formula_setting``（layer=template）；``base_definition`` 记录模板写入该公式位时的全局定义，
全局之后变了 ⇒ 模板管理里提示「模板与新全局不一致」，可一键并入（走模板发布）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.formula_setting_models import (
    FormulaPublish,
    FormulaSetting,
    FormulaSyncItem,
    FormulaTemplate,
    FormulaTemplateSubscription,
    FormulaTemplateVersion,
)
from app.services.formula_settings.audit import audit_global, change_entry
from app.services.formula_settings.definitions import (
    DOMAINS,
    exec_hash,
    get_spec,
    is_effectively_disabled,
    normalize,
    same_exec,
)
from app.services.formula_settings.domain_stores import validate_definition
from app.services.formula_settings.effective import effective_slots
from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.projects import VALID_STANDARDS
from app.services.formula_settings.publish import preview_global, publish_global, publish_to_dict
from app.services.formula_settings.stores import get_store
from app.services.formula_settings.template_access import SHARE_LABELS, Viewer, check_share_scope
from app.services.formula_settings.templates import template_rows

SOURCES = ("project", "global", "manual")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def global_scope(domain: str, applicable_scope: str | None) -> str | None:
    """模板适用范围 → 该域全局层的作用范围；无法确定（通用模板 / 口径不匹配）为 ``None``。"""
    kind = get_spec(domain).scope_kind
    if kind == "any":
        return "*"
    s = (applicable_scope or "").strip()
    if kind == "standard":
        return s if s in VALID_STANDARDS else None
    tt = s if s in ("soe", "listed") else s.partition("_")[0]
    return tt if tt in ("soe", "listed") else None


def _definition_with_structure(definition: Mapping[str, Any] | None, structure: Mapping | None) -> dict:
    d = dict(definition or {})
    if structure:
        d["_structure"] = dict(structure)
    return d


def template_to_dict(tpl: FormulaTemplate, *, viewer: Viewer | None = None) -> dict[str, Any]:
    return {
        "id": str(tpl.id), "name": tpl.name, "description": tpl.description,
        "share_scope": tpl.share_scope, "share_scope_label": SHARE_LABELS.get(tpl.share_scope, tpl.share_scope),
        "owner_user_id": str(tpl.owner_user_id) if tpl.owner_user_id else None,
        "owner_project_id": str(tpl.owner_project_id) if tpl.owner_project_id else None,
        "applicable_scope": tpl.applicable_scope, "domains": list(tpl.domains or []), "version": tpl.version,
        "status": tpl.status, "can_manage": viewer.can_manage(tpl) if viewer is not None else False,
        "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
    }


# ── 保存 ──────────────────────────────────────────────────────────────────────


async def _collect(db: AsyncSession, *, source: str, domains: list[str], applicable_scope: str,
                   source_project_id: uuid.UUID | None, slot_keys: Mapping[str, list[str]] | None,
                   items: list[Mapping[str, Any]] | None) -> dict[str, dict[str, dict]]:
    """``{domain: {slot_key: {"definition", "label", "base", "base_version"}}}``。"""
    out: dict[str, dict[str, dict]] = {}
    if source == "manual":
        for raw in items or []:
            domain, slot = str(raw.get("domain") or ""), str(raw.get("slot_key") or "").strip()
            get_spec(domain)
            if not slot or not isinstance(raw.get("definition"), Mapping):
                raise FormulaSettingError("手工录入的每条公式须有域、公式位与定义")
            out.setdefault(domain, {})[slot] = {"definition": dict(raw["definition"]),
                                                "label": str(raw.get("label") or slot)}
    for domain in domains:
        get_spec(domain)
        wanted = set(slot_keys.get(domain) or []) if slot_keys and slot_keys.get(domain) else None
        if source == "project":
            if source_project_id is None:
                raise FormulaSettingError("从项目保存模板须指定来源项目")
            for slot, e in (await effective_slots(db, domain, source_project_id)).items():
                if (wanted is not None and slot not in wanted) or (wanted is None and e.local is None):
                    continue  # 未指定公式位时只取本项目自己的定义（适配 / 订阅的模板）
                if e.definition is None or is_effectively_disabled(domain, e.definition):
                    continue
                up = e.upstream if e.upstream is not None and e.upstream.layer != "preset" else None
                out.setdefault(domain, {})[slot] = {
                    "definition": _definition_with_structure(e.definition, e.structure), "label": e.label,
                    "base": up.definition if up else None, "base_version": up.version if up else None}
        elif source == "global":
            scope = global_scope(domain, applicable_scope)
            if scope is None:
                raise FormulaSettingError(f"{get_spec(domain).label}：请先选择适用准则 / 模板类型")
            for slot, rec in (await get_store(domain).list_global(db, scope)).items():
                if wanted is not None and slot not in wanted:
                    continue
                out.setdefault(domain, {})[slot] = {
                    "definition": _definition_with_structure(rec.definition, rec.structure), "label": rec.label,
                    "base": rec.definition, "base_version": rec.version}
    return out


async def _fill_bases(db: AsyncSession, applicable_scope: str, entries: dict[str, dict[str, dict]]) -> None:
    """手工录入的公式位：基线取当前全局（之后全局再变才提示不一致）。"""
    for domain, slots in entries.items():
        scope = global_scope(domain, applicable_scope)
        current = await get_store(domain).list_global(db, scope) if scope else {}
        for slot, e in slots.items():
            if "base" not in e and slot in current:
                e["base"], e["base_version"] = current[slot].definition, current[slot].version


def _template_row(tpl_id: uuid.UUID, domain: str, slot: str, e: Mapping[str, Any], user_id) -> FormulaSetting:
    row = FormulaSetting(id=uuid.uuid4(), domain=domain, layer="template", scope="", template_id=tpl_id,
                         slot_key=slot, slot_label=e.get("label") or slot, definition=dict(e["definition"]),
                         version=1, created_by=user_id, updated_by=user_id)
    row.definition_hash = exec_hash(domain, row.definition)
    _set_base(row, e.get("base"), e.get("base_version"))
    return row


def _set_base(row: FormulaSetting, base: Mapping | None, base_version: int | None) -> None:
    row.base_definition = {k: v for k, v in dict(base).items() if k != "_structure"} if base is not None else None
    row.base_version = base_version if base is not None else None
    row.base_origin = "global" if base is not None else None


async def create_template(db: AsyncSession, *, viewer: Viewer, name: str, description: str | None,
                          share_scope: str, owner_project_id: uuid.UUID | None, applicable_scope: str,
                          source: str, domains: list[str], source_project_id: uuid.UUID | None = None,
                          slot_keys: Mapping[str, list[str]] | None = None,
                          items: list[Mapping[str, Any]] | None = None, note: str | None = None) -> FormulaTemplate:
    if source not in SOURCES:
        raise FormulaSettingError("模板来源须为 project / global / manual")
    if not (name or "").strip():
        raise FormulaSettingError("模板名称不能为空")
    check_share_scope(share_scope, owner_project_id, admin=viewer.admin)
    if source == "project" and not applicable_scope and source_project_id is not None:
        project = await db.get(Project, source_project_id)
        if project is not None:
            from app.services.formula_settings.projects import scope_of

            applicable_scope = scope_of("report", project.template_type, project.report_scope)
    entries = await _collect(db, source=source, domains=list(dict.fromkeys(domains)),
                             applicable_scope=applicable_scope, source_project_id=source_project_id,
                             slot_keys=slot_keys, items=items)
    entries = {d: s for d, s in entries.items() if s}
    if not entries:
        raise FormulaSettingError("没有可放进模板的公式（来源项目没有自己的公式时请指定公式位）")
    await _fill_bases(db, applicable_scope, entries)
    user_id = viewer.user.id
    tpl = FormulaTemplate(id=uuid.uuid4(), name=name.strip(), description=(description or "").strip() or None,
                          share_scope=share_scope, owner_user_id=user_id,
                          owner_project_id=owner_project_id if share_scope in ("team", "group") else None,
                          applicable_scope=applicable_scope or "", domains=sorted(entries), version=1,
                          status="active", created_by=user_id, updated_by=user_id, created_at=_now(),
                          updated_at=_now())
    db.add(tpl)
    await db.flush()
    for domain, slots in entries.items():
        for slot, e in slots.items():
            validate_definition(domain, e["definition"], f"{get_spec(domain).label} {e.get('label') or slot}", slot)
            db.add(_template_row(tpl.id, domain, slot, e, user_id))
    changes = [{"domain": d, "slot_key": s, "label": e.get("label") or s, "new": e["definition"]}
               for d, slots in entries.items() for s, e in slots.items()]
    db.add(FormulaTemplateVersion(id=uuid.uuid4(), template_id=tpl.id, version=1, note=note, published_by=user_id,
                                  snapshot={d: {s: e["definition"] for s, e in slots.items()}
                                            for d, slots in entries.items()},
                                  change_set=changes))
    await db.flush()
    await audit_global(db, user_id=user_id, domain=",".join(tpl.domains), scope=tpl.applicable_scope,
                       action="formula.template_saved", resource_id=tpl.id, details={
                           "template_id": str(tpl.id), "name": tpl.name, "share_scope": share_scope,
                           "source": source, "source_project_id": str(source_project_id) if source_project_id
                           else None, "slot_count": len(changes)})
    return tpl


# ── 改名 / 共享范围 / 删除 ────────────────────────────────────────────────────


async def active_subscriptions(db: AsyncSession, template_id: uuid.UUID) -> list[FormulaTemplateSubscription]:
    return list((await db.execute(sa.select(FormulaTemplateSubscription).where(
        FormulaTemplateSubscription.template_id == template_id,
        FormulaTemplateSubscription.is_active == sa.true()))).scalars().all())


async def update_meta(db: AsyncSession, tpl: FormulaTemplate, *, viewer: Viewer, changes: Mapping[str, Any]) -> None:
    """只改名称、说明、共享范围、所属项目、适用范围；定义改动走发布新版本。"""
    if "name" in changes:
        if not str(changes["name"] or "").strip():
            raise FormulaSettingError("模板名称不能为空")
        tpl.name = str(changes["name"]).strip()
    if "description" in changes:
        tpl.description = (changes["description"] or "").strip() or None
    if "share_scope" in changes or "owner_project_id" in changes:
        scope = changes.get("share_scope", tpl.share_scope)
        owner = changes.get("owner_project_id", tpl.owner_project_id)
        check_share_scope(scope, owner, admin=viewer.admin)
        tpl.share_scope, tpl.owner_project_id = scope, owner if scope in ("team", "group") else None
    if "applicable_scope" in changes and (changes["applicable_scope"] or "") != tpl.applicable_scope:
        if await active_subscriptions(db, tpl.id):
            raise FormulaSettingError("已有项目订阅该模板，不能修改适用准则", status_code=409)
        tpl.applicable_scope = changes["applicable_scope"] or ""
    tpl.updated_by, tpl.updated_at = viewer.user.id, _now()
    await db.flush()
    await audit_global(db, user_id=viewer.user.id, domain=",".join(tpl.domains or []), scope=tpl.applicable_scope,
                       action="formula.template_updated", resource_id=tpl.id,
                       details={"template_id": str(tpl.id), "changes": {k: str(v) for k, v in changes.items()}})


async def delete_template(db: AsyncSession, tpl: FormulaTemplate, *, user_id: uuid.UUID | None) -> None:
    subs = await active_subscriptions(db, tpl.id)
    if subs:
        raise FormulaSettingError(f"还有 {len(subs)} 个项目订阅该模板，请先让这些项目退订", status_code=409,
                                  code="FORMULA_TEMPLATE_IN_USE")
    tpl.is_deleted, tpl.updated_by, tpl.updated_at = True, user_id, _now()
    await db.execute(sa.update(FormulaSetting).where(
        FormulaSetting.layer == "template", FormulaSetting.template_id == tpl.id,
    ).values(is_deleted=True, updated_by=user_id).execution_options(synchronize_session=False))
    await db.flush()
    await audit_global(db, user_id=user_id, domain=",".join(tpl.domains or []), scope=tpl.applicable_scope,
                       action="formula.template_deleted", resource_id=tpl.id,
                       details={"template_id": str(tpl.id), "name": tpl.name})


# ── 详情 / 版本 / 订阅者 ──────────────────────────────────────────────────────


async def template_definitions(db: AsyncSession, tpl: FormulaTemplate) -> dict[str, dict[str, FormulaSetting]]:
    return {d: await template_rows(db, tpl.id, d) for d in (tpl.domains or []) if d in DOMAINS}


async def global_hints(db: AsyncSession, tpl: FormulaTemplate,
                       rows: Mapping[str, Mapping[str, FormulaSetting]]) -> list[dict[str, Any]]:
    """模板写入后全局又变了的公式位（R13.6）：模板定义 / 模板写入时的全局 / 当前全局。"""
    out = []
    for domain, slots in rows.items():
        scope = global_scope(domain, tpl.applicable_scope)
        if scope is None:
            continue
        current = await get_store(domain).list_global(db, scope)
        for slot, row in sorted(slots.items()):
            now = current.get(slot)
            if now is None or same_exec(domain, row.base_definition, now.definition):
                continue
            out.append({"domain": domain, "slot_key": slot, "label": row.slot_label or slot,
                        "template_definition": _public(row.definition), "base_definition": row.base_definition,
                        "global_definition": _public(now.definition), "global_version": now.version,
                        "same_as_template": same_exec(domain, row.definition, now.definition)})
    return out


def _public(d: Mapping | None) -> dict | None:
    return None if d is None else {k: v for k, v in dict(d).items() if k != "_structure"}


async def template_detail(db: AsyncSession, tpl: FormulaTemplate, *, viewer: Viewer) -> dict[str, Any]:
    rows = await template_definitions(db, tpl)
    return {
        **template_to_dict(tpl, viewer=viewer),
        "definitions": {d: [{"slot_key": s, "label": r.slot_label or s, "definition": _public(r.definition),
                             "structure": (r.definition or {}).get("_structure") or {}, "version": r.version}
                            for s, r in sorted(slots.items())] for d, slots in rows.items()},
        "global_hints": await global_hints(db, tpl, rows),
        "subscriber_count": len(await active_subscriptions(db, tpl.id)),
    }


async def template_versions(db: AsyncSession, tpl: FormulaTemplate) -> list[dict[str, Any]]:
    rows = (await db.execute(sa.select(FormulaTemplateVersion).where(
        FormulaTemplateVersion.template_id == tpl.id).order_by(FormulaTemplateVersion.version.desc()))).scalars()
    return [{"version": r.version, "note": r.note, "change_set": r.change_set or [],
             "published_by": str(r.published_by) if r.published_by else None,
             "published_at": r.published_at.isoformat() if r.published_at else None} for r in rows]


async def template_subscribers(db: AsyncSession, tpl: FormulaTemplate) -> list[dict[str, Any]]:
    """订阅项目、订阅版本、是否暂缓、本地改过的公式位数（三方比较）、待确认事项数（R13.8）。"""
    out = []
    for sub in await active_subscriptions(db, tpl.id):
        project = await db.get(Project, sub.project_id)
        local = await get_store(sub.domain).list_project(db, sub.project_id)
        modified = sum(1 for lo in local.values() if lo.base_origin == "template" and lo.base_template_id == tpl.id
                       and not same_exec(sub.domain, lo.definition, lo.base_definition))
        pending = await db.scalar(sa.select(sa.func.count()).select_from(FormulaSyncItem).where(
            FormulaSyncItem.project_id == sub.project_id, FormulaSyncItem.domain == sub.domain,
            FormulaSyncItem.status == "pending", FormulaSyncItem.upstream_template_id == tpl.id))
        out.append({"project_id": str(sub.project_id), "project_name": project.name if project else "",
                    "domain": sub.domain, "template_version": sub.template_version, "pinned": sub.pinned,
                    "behind": sub.template_version < tpl.version, "local_modified": modified,
                    "pending": int(pending or 0),
                    "subscribed_at": sub.subscribed_at.isoformat() if sub.subscribed_at else None})
    return out


# ── 设为全局 / 全局候选（R13.7） ─────────────────────────────────────────────


async def _promote_changes(db: AsyncSession, tpl: FormulaTemplate, domain: str,
                           slot_keys: list[str] | None) -> tuple[str, list[dict[str, Any]]]:
    if domain not in (tpl.domains or []):
        raise FormulaSettingError("模板里没有这个域的公式")
    scope = global_scope(domain, tpl.applicable_scope)
    if scope is None:
        raise FormulaSettingError("通用模板设为全局前请先设置适用准则 / 模板类型")
    rows = await template_rows(db, tpl.id, domain)
    current = await get_store(domain).list_global_exact(db, scope)
    changes = []
    for slot, row in sorted(rows.items()):
        if slot_keys and slot not in slot_keys:
            continue
        d = dict(row.definition or {})
        changes.append({"slot_key": slot, "definition": _public(d), "label": row.slot_label or slot,
                        "structure": d.get("_structure") or None,
                        "expected_version": current[slot].version if slot in current else None})
    if not changes:
        raise FormulaSettingError("没有要设为全局的公式")
    return scope, changes


async def promote_preview(db: AsyncSession, tpl: FormulaTemplate, *, domain: str,
                          slot_keys: list[str] | None = None) -> dict[str, Any]:
    scope, changes = await _promote_changes(db, tpl, domain, slot_keys)
    return await preview_global(db, domain=domain, scope=scope, changes=changes)


async def promote(db: AsyncSession, tpl: FormulaTemplate, *, viewer: Viewer, domain: str,
                  slot_keys: list[str] | None = None, decisions=None, request_id: str | None = None,
                  note: str | None = None) -> dict[str, Any]:
    """admin：作为全局发布（预览 / 决策同全局发布）；其他人：提交全局候选，admin 审核后发布。"""
    scope, changes = await _promote_changes(db, tpl, domain, slot_keys)
    if viewer.admin:
        result = await publish_global(db, domain=domain, scope=scope, changes=changes, user_id=viewer.user.id,
                                      decisions=decisions, request_id=request_id, source="template_promote",
                                      note=note or f"公式模板「{tpl.name}」设为全局")
        return {**result, "template_id": str(tpl.id)}
    if request_id:
        replay = (await db.execute(sa.select(FormulaPublish).where(FormulaPublish.request_id == request_id))
                  ).scalars().first()
        if replay is not None:
            return {"candidate": publish_to_dict(replay), "idempotent": True, "events": []}
    current = await get_store(domain).list_global_exact(db, scope)
    row = FormulaPublish(id=uuid.uuid4(), domain=domain, scope=scope, target="global", template_id=tpl.id,
                         source="candidate", request_id=request_id, status="pending", published_by=viewer.user.id,
                         note=note or f"公式模板「{tpl.name}」提交为全局候选", summary={},
                         change_set=[{**c, "old": _public(current[c["slot_key"]].definition)
                                      if c["slot_key"] in current else None, "new": c["definition"],
                                      "old_version": c["expected_version"]} for c in changes])
    db.add(row)
    await db.flush()
    await audit_global(db, user_id=viewer.user.id, domain=domain, scope=scope, action="formula.template_candidate",
                       resource_id=row.id, details={"template_id": str(tpl.id), "publish_id": str(row.id),
                                                    "changes": [change_entry(domain, c["slot_key"], None,
                                                                             c["definition"]) for c in changes]})
    return {"candidate": publish_to_dict(row), "idempotent": False, "events": []}


def normalized_equal(domain: str, a: Mapping | None, b: Mapping | None) -> bool:
    return normalize(domain, a) == normalize(domain, b)
