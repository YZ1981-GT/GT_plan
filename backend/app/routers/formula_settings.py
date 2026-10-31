"""公式全局设置 / 本项目适配 / 待确认 / 应用到其他（spec formula-global-settings-sync，design §10）。

权限（R11.1）：读全局 = 登录；读项目有效定义与待确认 = 项目 readonly；写本项目、处理待确认、应用到指定项目
= 每个目标项目 edit；写全局 / 发布 / 设为全局 / 审核候选 = admin。拒绝时零写入、零事件（R11.2）。
发布记录 = 登录，结果按查看人过滤（spec formula-hub-integrity-closure 需求 7.4，ADR-FHIC-20）。
服务层只 flush，这里 commit 之后才发变更事件（R8.1）。
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user, require_project_access
from app.models.core import User
from app.services.formula_settings import apply_ops, project_ops
from app.services.formula_settings.definitions import DOMAINS, UnknownDomain, get_spec
from app.services.formula_settings.effective import effective_slots, upstream_records
from app.services.formula_settings.engine import Decisions
from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.pending import item_to_dict, list_pending
from app.services.formula_settings.projects import VALID_STANDARDS, get_project
from app.services.formula_settings.propagation import publish_events
from app.services.formula_settings.publish import list_publishes, preview_global, publish_global
from app.services.formula_settings.stores import get_store
from app.services.formula_settings.template_access import Viewer

router = APIRouter(prefix="/api/formula-settings", tags=["formula-settings"])
project_router = APIRouter(prefix="/api/projects/{project_id}/formula-settings", tags=["formula-settings"])

from app.services.formula_settings.consumers import READER_ENTRIES, wired_domains as _wired_domains

#: 运行时缓存（进程内不变）
_WIRED_CACHE: set[str] | None = None


def _wired_set() -> set[str]:
    global _WIRED_CACHE  # noqa: PLW0603
    if _WIRED_CACHE is None:
        _WIRED_CACHE = _wired_domains()
    return _WIRED_CACHE
#: 界面默认选第一个作用范围：常用准则在前，enterprise 只是「项目配置不在合法集合」时的兜底口径，放最后
_STANDARD_ORDER = ["soe_standalone", "soe_consolidated", "listed_standalone", "listed_consolidated", "enterprise"]
_SCOPE_OPTIONS = {
    "standard": _STANDARD_ORDER,
    "template_type": ["soe", "listed"],
    "consolidated_template_type": ["soe", "listed"],
    "any": ["*"],
}
_SCOPE_LABELS = {
    "soe_standalone": "国企单体", "soe_consolidated": "国企合并", "listed_standalone": "上市单体",
    "listed_consolidated": "上市合并", "enterprise": "企业会计准则（通用）", "soe": "国企版", "listed": "上市版",
    "*": "全部（通用）",
}


# ── 请求体 ────────────────────────────────────────────────────────────────────


class ChangeIn(BaseModel):
    slot_key: str = Field(min_length=1, max_length=300)
    definition: dict[str, Any] | None = None
    expected_version: int | None = None
    label: str = Field("", max_length=300)
    structure: dict[str, Any] | None = None


class DecisionsIn(BaseModel):
    project_choices: dict[str, Literal["apply", "defer"]] = Field(default_factory=dict)
    conflict_choices: dict[str, Literal["adopt", "keep", "ask"]] = Field(default_factory=dict)
    default_conflict: Literal["adopt", "keep", "ask"] = "ask"

    def to_decisions(self) -> Decisions:
        return Decisions.parse(self.model_dump())


class PreviewBody(BaseModel):
    scope: str = Field(min_length=1, max_length=40)
    changes: list[ChangeIn] = Field(min_length=1, max_length=2000)


class PublishBody(PreviewBody):
    decisions: DecisionsIn = Field(default_factory=DecisionsIn)
    request_id: str | None = Field(None, max_length=64)
    note: str | None = Field(None, max_length=2000)


class OverrideItem(BaseModel):
    slot_key: str = Field(min_length=1, max_length=300)
    definition: dict[str, Any]
    expected_version: int | None = None
    label: str = Field("", max_length=300)
    structure: dict[str, Any] | None = None


class OverridesBody(BaseModel):
    items: list[OverrideItem] = Field(min_length=1, max_length=2000)


class ResolutionIn(BaseModel):
    item_id: str = Field(min_length=1, max_length=64)
    choice: Literal["adopt", "keep", "custom"]
    #: 列表给出的修订号（ADR-FHIC-11）：缺失由服务层判 428（这里设必填会变成 422），与当前不等 409
    revision: int | None = Field(None, ge=1)
    custom_definition: dict[str, Any] | None = None


class ResolveBody(BaseModel):
    resolutions: list[ResolutionIn] = Field(min_length=1, max_length=2000)


class ApplyBody(BaseModel):
    target: Literal["global", "candidate", "projects"]
    slot_keys: list[str] = Field(min_length=1, max_length=2000)
    project_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    decisions: DecisionsIn = Field(default_factory=DecisionsIn)
    request_id: str | None = Field(None, max_length=64)
    note: str | None = Field(None, max_length=2000)


class ReviewBody(BaseModel):
    approve: bool
    decisions: DecisionsIn = Field(default_factory=DecisionsIn)
    note: str | None = Field(None, max_length=2000)


# ── 公共 ──────────────────────────────────────────────────────────────────────


def _is_admin(user: User) -> bool:
    from app.services.formula_settings.permissions import can_edit_global
    return can_edit_global(user)


def _require_admin(user: User) -> None:
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail={
            "error_code": "FORMULA_SETTING_FORBIDDEN", "message": "全局公式设置仅管理员可修改"})


def _domain(domain: str) -> str:
    try:
        get_spec(domain)
    except UnknownDomain:
        raise HTTPException(status_code=404, detail={
            "error_code": "FORMULA_SETTING_DOMAIN_UNKNOWN", "message": f"公式域不存在：{domain}"}) from None
    return domain


def _http(exc: FormulaSettingError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.to_detail())


async def _run(db: AsyncSession, coro):
    """执行服务调用：业务错误回滚并转 HTTP；成功则 commit。"""
    try:
        result = await coro
    except FormulaSettingError as exc:
        await db.rollback()
        raise _http(exc) from None
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail={"error_code": "FORMULA_SETTING_INVALID",
                                                     "message": str(exc)}) from None
    await db.commit()
    return result


async def _emit(result: dict[str, Any], *, domain: str, source: str) -> None:
    await publish_events(result.get("events") or [], domain=domain, source=source,
                         token=result.get("publish_id"))


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in result.items() if k != "events"} | {
        "changed_project_count": len(result.get("events") or [])}


# ── 全局 ──────────────────────────────────────────────────────────────────────


@router.get("/domains")
async def list_domains(current_user: User = Depends(get_current_user)):
    wired = _wired_set()
    domains_out = []
    for s in DOMAINS.values():
        entry = {
            "key": s.key,
            "label": s.label,
            "scope_kind": s.scope_kind,
            "wired": s.key in wired,
            "scopes": [{"value": v, "label": _SCOPE_LABELS.get(v, v)} for v in (
                _SCOPE_OPTIONS[s.scope_kind] + (["*"] if s.key == "cross_check" else []))],
            "exec_fields": list(s.exec_fields),
            "desc_fields": list(s.desc_fields),
        }
        # tb_detail 无读者时附中文说明（需求 15.4）
        if s.key in READER_ENTRIES and not READER_ENTRIES[s.key]:
            entry["wired_reason"] = "该域暂无生产消费方读取有效定义"
        domains_out.append(entry)
    return {"domains": domains_out, "is_admin": _is_admin(current_user)}


@router.get("/publishes")
async def get_publishes(domain: str | None = Query(None, max_length=32), scope: str | None = Query(None, max_length=40),
                        status: Literal["published", "pending", "rejected"] | None = Query(None),
                        limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """发布记录：任何登录用户可调，结果按查看人过滤并裁掉他项目信息（需求 7.4，ADR-FHIC-20）。"""
    if domain:
        _domain(domain)
    viewer = await Viewer.load(db, current_user)
    return {"items": await list_publishes(db, viewer=viewer, domain=domain, scope=scope, status=status, limit=limit)}


@router.post("/candidates/{publish_id}/preview")
async def preview_candidate(publish_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    try:
        return await apply_ops.candidate_preview(db, publish_id)
    except FormulaSettingError as exc:
        raise _http(exc) from None


@router.post("/candidates/{publish_id}/review")
async def review_candidate(publish_id: uuid.UUID, body: ReviewBody, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    result = await _run(db, apply_ops.review_candidate(db, publish_id=publish_id, approve=body.approve,
                                                       user_id=current_user.id,
                                                       decisions=body.decisions.to_decisions(), note=body.note))
    domain = (result.get("candidate") or {}).get("domain") or "report"
    if result.pop("custom_presets_changed", False):  # 自定义公式预设：本进程缓存立即刷新
        from app.services.formula_settings.custom_presets import refresh_cache

        await refresh_cache(db)
    await _emit(result, domain=domain, source="candidate")
    return _public_result(result)


@router.get("/{domain}/global")
async def get_global(domain: str, scope: str = Query(..., min_length=1, max_length=40),
                     db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    _domain(domain)
    records = await upstream_records(db, get_store(domain), scope)
    return {"domain": domain, "scope": scope, "can_edit": _is_admin(current_user), "slots": [
        {"slot_key": k, "label": r.label, "layer": r.layer or "global", "definition": _plain(r.definition),
         "version": r.version if r.layer != "preset" else None, "structure": r.structure}
        for k, r in sorted(records.items())]}


def _plain(d: dict | None) -> dict | None:
    return None if d is None else {k: v for k, v in d.items() if k != "_structure"}


@router.post("/{domain}/global/preview")
async def preview(domain: str, body: PreviewBody, db: AsyncSession = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    _domain(domain)
    try:
        return await preview_global(db, domain=domain, scope=body.scope,
                                    changes=[c.model_dump() for c in body.changes])
    except FormulaSettingError as exc:
        raise _http(exc) from None


@router.post("/{domain}/global/publish")
async def publish(domain: str, body: PublishBody, db: AsyncSession = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    _domain(domain)
    result = await _run(db, publish_global(
        db, domain=domain, scope=body.scope, changes=[c.model_dump() for c in body.changes],
        user_id=current_user.id, decisions=body.decisions.to_decisions(), request_id=body.request_id,
        source="global_edit", note=body.note))
    await _emit(result, domain=domain, source="global_edit")
    return _public_result(result)


# ── 项目 ──────────────────────────────────────────────────────────────────────


@project_router.get("/pending")
async def get_pending(project_id: uuid.UUID, domain: str | None = Query(None, max_length=32),
                      db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_project_access("readonly"))):
    if domain:
        _domain(domain)
    items = [item_to_dict(i) for i in await list_pending(db, project_id, domain)]
    return {"project_id": str(project_id), "count": len(items), "items": items}


@project_router.post("/pending/resolve")
async def resolve(project_id: uuid.UUID, body: ResolveBody, db: AsyncSession = Depends(get_db),
                  current_user: User = Depends(require_project_access("edit"))):
    """处理待确认：每条回传列表里的 ``revision``；缺 428、已被覆盖或已处理 409，整体回滚（需求 8.2）。"""
    result = await _run(db, project_ops.resolve_items(
        db, project_id=project_id, resolutions=[r.model_dump() for r in body.resolutions], user_id=current_user.id))
    events = result.get("events") or []
    for ev in events:
        await publish_events([ev], domain=ev["domain"], source="project_resolve")
    # recalc_domains：有效定义真的变了、会重算的域（全选「保留本项目」时为空 ⇒ 前端不能说「会按新定义重算」）
    return {**{k: v for k, v in result.items() if k != "events"},
            "recalc_domains": sorted({ev["domain"] for ev in events})}


@project_router.get("/apply-targets")
async def apply_targets(project_id: uuid.UUID, domain: str = Query("report", max_length=32),
                        db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_project_access("readonly"))):
    """「应用到指定项目」可选的目标：当前用户有 edit 权限、未归档的其他项目（R7.3）。"""
    from app.models.base import PermissionLevel, ProjectStatus
    from app.models.core import Project, ProjectUser

    _domain(domain)
    source = await get_project(db, domain, project_id)
    q = sa.select(Project.id, Project.name).where(Project.is_deleted == sa.false(), Project.id != project_id,
                                                  Project.status != ProjectStatus.archived)
    if not _is_admin(current_user):
        q = q.where(Project.id.in_(sa.select(ProjectUser.project_id).where(
            ProjectUser.user_id == current_user.id, ProjectUser.is_deleted == sa.false(),
            ProjectUser.permission_level == PermissionLevel.edit)))
    rows = (await db.execute(q.order_by(Project.name))).all()
    from app.services.formula_settings.projects import list_projects

    infos = {p.id: p for p in await list_projects(db, domain, ids=[r[0] for r in rows])}
    return {"items": [{"project_id": str(pid), "name": name, "scope": infos[pid].scope if pid in infos else "",
                       "same_scope": source is not None and pid in infos and infos[pid].scope == source.scope}
                      for pid, name in rows if pid in infos]}


@project_router.get("/{domain}/effective")
async def get_effective(project_id: uuid.UUID, domain: str, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_project_access("readonly"))):
    _domain(domain)
    project = await get_project(db, domain, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error_code": "FORMULA_SETTING_NOT_FOUND",
                                                     "message": "项目不存在或已删除"})
    slots = await effective_slots(db, domain, project_id, scope=project.scope)
    return {"domain": domain, "project_id": str(project_id), "scope": project.scope, "frozen": project.frozen,
            "can_edit_global": _is_admin(current_user), "slots": [s.to_dict() for s in slots.values()]}


@project_router.put("/{domain}/overrides")
async def save_overrides(project_id: uuid.UUID, domain: str, body: OverridesBody, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_project_access("edit"))):
    _domain(domain)
    result = await _run(db, project_ops.save_overrides(
        db, domain=domain, project_id=project_id, items=[i.model_dump() for i in body.items],
        user_id=current_user.id))
    await _emit(result, domain=domain, source="project_edit")
    return {k: v for k, v in result.items() if k != "events"}


@project_router.delete("/{domain}/overrides")
async def restore_global(project_id: uuid.UUID, domain: str,
                         slot_key: list[str] = Query(..., min_length=1, max_length=2000),
                         expected_version: list[int] | None = Query(None),
                         db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_project_access("edit"))):
    _domain(domain)
    # ADR-FHIC-11：重复 Query 参数按序配对；缺 428、个数不等 422
    if expected_version is None:
        raise HTTPException(status_code=428, detail={
            "error_code": "FORMULA_VERSION_REQUIRED",
            "message": "删除本项目适配必须带版本号，请刷新后重试"})
    if len(expected_version) != len(slot_key):
        raise HTTPException(status_code=422, detail={
            "error_code": "FORMULA_SETTING_INVALID",
            "message": f"expected_version 个数（{len(expected_version)}）与 slot_key 个数（{len(slot_key)}）不一致"})
    result = await _run(db, project_ops.restore_global(db, domain=domain, project_id=project_id,
                                                       slot_keys=slot_key, user_id=current_user.id,
                                                       expected_versions=expected_version))
    await _emit(result, domain=domain, source="project_restore")
    return {k: v for k, v in result.items() if k != "events"}


async def _authorize_targets(db: AsyncSession, user: User, project_ids: list[uuid.UUID]) -> None:
    for pid in project_ids:
        try:
            await assert_project_permission(db, user, pid, "edit")
        except HTTPException as exc:
            raise HTTPException(status_code=exc.status_code, detail={
                "error_code": "FORMULA_SETTING_FORBIDDEN", "message": "没有目标项目的编辑权限",
                "project_id": str(pid)}) from None


@project_router.post("/{domain}/apply-preview")
async def apply_preview(project_id: uuid.UUID, domain: str, body: ApplyBody, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_project_access("edit"))):
    _domain(domain)
    try:
        if body.target == "global":
            _require_admin(current_user)
            return await apply_ops.promote_preview(db, domain=domain, project_id=project_id,
                                                   slot_keys=body.slot_keys)
        if body.target == "candidate":
            return await apply_ops.promote_preview(db, domain=domain, project_id=project_id,
                                                   slot_keys=body.slot_keys)
        if not body.project_ids:
            raise FormulaSettingError("请选择要应用到的项目")
        await _authorize_targets(db, current_user, body.project_ids)
        return await apply_ops.apply_preview(db, domain=domain, project_id=project_id, slot_keys=body.slot_keys,
                                             target_ids=body.project_ids)
    except FormulaSettingError as exc:
        raise _http(exc) from None


@project_router.post("/{domain}/apply")
async def apply(project_id: uuid.UUID, domain: str, body: ApplyBody, db: AsyncSession = Depends(get_db),
                current_user: User = Depends(require_project_access("edit"))):
    _domain(domain)
    decisions = body.decisions.to_decisions()
    if body.target in ("global", "candidate"):
        if body.target == "global":
            _require_admin(current_user)
        result = await _run(db, apply_ops.promote(
            db, domain=domain, project_id=project_id, slot_keys=body.slot_keys,
            is_admin=body.target == "global", user_id=current_user.id, decisions=decisions,
            request_id=body.request_id, note=body.note))
        await _emit(result, domain=domain, source="promote")
        return _public_result(result)
    if not body.project_ids:
        raise HTTPException(status_code=400, detail={"error_code": "FORMULA_SETTING_INVALID",
                                                     "message": "请选择要应用到的项目"})
    await _authorize_targets(db, current_user, body.project_ids)
    result = await _run(db, apply_ops.apply_to_projects(
        db, domain=domain, project_id=project_id, slot_keys=body.slot_keys, target_ids=body.project_ids,
        decisions=decisions, user_id=current_user.id, request_id=body.request_id))
    await _emit(result, domain=domain, source="apply_to_projects")
    return _public_result(result)


# ── G 批：公式依赖关系查询 ────────────────────────────────────────────────
# spec: formula-management-ux-improvements · G 批；口径修正见 formula-settings-wiring-closure R3.2


@project_router.get("/dependencies")
async def formula_dependencies(
    project_id: uuid.UUID,
    addr_id: str = Query(..., max_length=300,
                         description="report:{报表类型}:{行次} / {报表类型}:{行次} / 行次 / tb:{科目编码}"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """一条公式的上游引用与下游被引用（按本项目有效定义精确匹配，只读）。"""
    from app.services.formula_settings.dependencies import DependencyTargetError
    from app.services.formula_settings.dependencies import formula_dependencies as resolve

    try:
        return await resolve(db, project_id, addr_id)
    except DependencyTargetError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "FORMULA_DEPENDENCY_TARGET_NOT_FOUND",
                                                     "message": str(exc)}) from None
