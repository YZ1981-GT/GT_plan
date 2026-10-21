"""公式模板（R13，design §16.4）。

权限：列表 / 详情 / 版本 = 可见即可（不可见按不存在 404）；订阅者、改名、删除、发布新版本 = 所有者或 admin；
创建事务所模板 = admin，项目组 / 集团模板 = 所属项目 edit；从项目保存 = 来源项目 readonly；
设为全局 = admin（其他可见者 = 提交全局候选）；订阅 / 退订 = 目标项目 edit。
服务层只 flush，这里 commit 之后才发变更事件。模板操作只写模板层与本项目层，绝不写全局行（全局只经发布）。
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user, require_project_access
from app.models.core import User
from app.models.formula_setting_models import FormulaTemplate, FormulaTemplateSubscription
from app.routers.formula_settings import DecisionsIn, _http, _public_result, _run
from app.services.formula_settings import template_service as svc
from app.services.formula_settings import template_sync as sync
from app.services.formula_settings.errors import Forbidden, FormulaSettingError
from app.services.formula_settings.propagation import publish_events
from app.services.formula_settings.template_access import Viewer, get_managed, get_visible, list_visible

router = APIRouter(prefix="/api/formula-templates", tags=["formula-templates"])
project_router = APIRouter(prefix="/api/projects/{project_id}/formula-templates", tags=["formula-templates"])


class ManualItem(BaseModel):
    domain: str = Field(min_length=1, max_length=32)
    slot_key: str = Field(min_length=1, max_length=300)
    definition: dict[str, Any]
    label: str = Field("", max_length=300)


class CreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    share_scope: Literal["personal", "team", "group", "firm"] = "personal"
    owner_project_id: uuid.UUID | None = None
    applicable_scope: str = Field("", max_length=40)
    source: Literal["project", "global", "manual"]
    source_project_id: uuid.UUID | None = None
    domains: list[str] = Field(default_factory=list, max_length=10)
    slot_keys: dict[str, list[str]] | None = None
    items: list[ManualItem] = Field(default_factory=list, max_length=5000)
    note: str | None = Field(None, max_length=2000)


class UpdateBody(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    share_scope: Literal["personal", "team", "group", "firm"] | None = None
    owner_project_id: uuid.UUID | None = None
    applicable_scope: str | None = Field(None, max_length=40)


class TemplateChange(BaseModel):
    domain: str = Field(min_length=1, max_length=32)
    slot_key: str = Field(min_length=1, max_length=300)
    definition: dict[str, Any] | None = None


class PublishBody(BaseModel):
    expected_version: int | None = None
    changes: list[TemplateChange] = Field(min_length=1, max_length=5000)
    decisions: DecisionsIn = Field(default_factory=DecisionsIn)
    request_id: str | None = Field(None, max_length=64)
    note: str | None = Field(None, max_length=2000)


class PromoteBody(BaseModel):
    domain: str = Field(min_length=1, max_length=32)
    slot_keys: list[str] | None = Field(None, max_length=5000)
    decisions: DecisionsIn = Field(default_factory=DecisionsIn)
    request_id: str | None = Field(None, max_length=64)
    note: str | None = Field(None, max_length=2000)


class SubscribeBody(BaseModel):
    template_id: uuid.UUID
    domain: str = Field(min_length=1, max_length=32)
    decisions: DecisionsIn = Field(default_factory=DecisionsIn)


class UnsubscribeBody(BaseModel):
    domain: str = Field(min_length=1, max_length=32)
    mode: Literal["keep", "global"] = "global"
    decisions: DecisionsIn = Field(default_factory=DecisionsIn)


async def _viewer(db: AsyncSession, user: User) -> Viewer:
    return await Viewer.load(db, user)


async def _call(coro):
    """只读调用：业务错误转 HTTP。"""
    try:
        return await coro
    except FormulaSettingError as exc:
        raise _http(exc) from None


async def _emit(result: dict[str, Any], source: str) -> dict[str, Any]:
    await publish_events(result.get("events") or [], domain="template", source=source,
                         token=result.get("publish_id"))
    return _public_result(result)


# ── 模板 ──────────────────────────────────────────────────────────────────────


@router.get("")
async def list_templates(domain: str | None = Query(None, max_length=32), scope: str | None = Query(None, max_length=40),
                         db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    viewer = await _viewer(db, current_user)
    rows = await list_visible(db, viewer, domain=domain, scope=scope)
    # 批量统计每个模板的活跃订阅数（优化建议 #4：模板发现与推荐增强）
    sub_counts: dict[str, int] = {}
    if rows:
        tpl_ids = [t.id for t in rows]
        count_rows = (await db.execute(
            sa.select(
                FormulaTemplateSubscription.template_id,
                sa.func.count().label("cnt"),
            ).where(
                FormulaTemplateSubscription.template_id.in_(tpl_ids),
                FormulaTemplateSubscription.is_active == sa.true(),
            ).group_by(FormulaTemplateSubscription.template_id)
        )).all()
        sub_counts = {str(r[0]): r[1] for r in count_rows}
    items = []
    for t in rows:
        d = svc.template_to_dict(t, viewer=viewer)
        d["subscriber_count"] = sub_counts.get(str(t.id), 0)
        items.append(d)
    return {"items": items, "is_admin": viewer.admin}


@router.post("", status_code=201)
async def create_template(body: CreateBody, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    if body.share_scope in ("team", "group") and body.owner_project_id is not None:
        await assert_project_permission(db, current_user, body.owner_project_id, "edit")
    if body.source == "project" and body.source_project_id is not None:
        await assert_project_permission(db, current_user, body.source_project_id, "readonly")
    viewer = await _viewer(db, current_user)
    tpl = await _run(db, svc.create_template(
        db, viewer=viewer, name=body.name, description=body.description, share_scope=body.share_scope,
        owner_project_id=body.owner_project_id, applicable_scope=body.applicable_scope, source=body.source,
        domains=body.domains or sorted({i.domain for i in body.items}), source_project_id=body.source_project_id,
        slot_keys=body.slot_keys, items=[i.model_dump() for i in body.items], note=body.note))
    return await _call(svc.template_detail(db, tpl, viewer=viewer))


@router.get("/{template_id}")
async def get_template(template_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    viewer = await _viewer(db, current_user)
    tpl = await _call(get_visible(db, viewer, template_id))
    return await _call(svc.template_detail(db, tpl, viewer=viewer))


@router.get("/{template_id}/versions")
async def get_versions(template_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    tpl = await _call(get_visible(db, await _viewer(db, current_user), template_id))
    return {"items": await svc.template_versions(db, tpl)}


@router.get("/{template_id}/subscribers")
async def get_subscribers(template_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    tpl = await _call(get_managed(db, await _viewer(db, current_user), template_id))
    return {"items": await svc.template_subscribers(db, tpl)}


@router.put("/{template_id}")
async def update_template(template_id: uuid.UUID, body: UpdateBody, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    viewer = await _viewer(db, current_user)
    tpl = await _call(get_managed(db, viewer, template_id))
    changes = body.model_dump(exclude_unset=True)
    owner = changes.get("owner_project_id", tpl.owner_project_id)
    if changes.get("share_scope", tpl.share_scope) in ("team", "group") and owner is not None and (
            "share_scope" in changes or "owner_project_id" in changes):
        await assert_project_permission(db, current_user, owner, "edit")
    await _run(db, svc.update_meta(db, tpl, viewer=viewer, changes=changes))
    return await _call(svc.template_detail(db, tpl, viewer=viewer))


@router.delete("/{template_id}")
async def delete_template(template_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    tpl = await _call(get_managed(db, await _viewer(db, current_user), template_id))
    await _run(db, svc.delete_template(db, tpl, user_id=current_user.id))
    return {"id": str(template_id), "deleted": True}


@router.post("/{template_id}/publish-preview")
async def publish_preview(template_id: uuid.UUID, body: PublishBody, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    tpl = await _call(get_managed(db, await _viewer(db, current_user), template_id))
    return await _call(sync.publish_preview(db, tpl, changes=[c.model_dump() for c in body.changes],
                                            expected_version=body.expected_version))


@router.post("/{template_id}/publish")
async def publish(template_id: uuid.UUID, body: PublishBody, db: AsyncSession = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    tpl = await _call(get_managed(db, await _viewer(db, current_user), template_id))
    result = await _run(db, sync.publish_template(
        db, tpl, changes=[c.model_dump() for c in body.changes], expected_version=body.expected_version,
        user_id=current_user.id, decisions=body.decisions.to_decisions(), request_id=body.request_id,
        note=body.note))
    return await _emit(result, "template_publish")


@router.post("/{template_id}/promote-preview")
async def promote_preview(template_id: uuid.UUID, body: PromoteBody, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    viewer = await _viewer(db, current_user)
    if not viewer.admin:
        raise _http(Forbidden("设为全局仅管理员可操作；其他人可提交为全局候选"))
    tpl = await _call(get_visible(db, viewer, template_id))
    return await _call(svc.promote_preview(db, tpl, domain=body.domain, slot_keys=body.slot_keys))


@router.post("/{template_id}/promote")
async def promote(template_id: uuid.UUID, body: PromoteBody, db: AsyncSession = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    viewer = await _viewer(db, current_user)
    tpl = await _call(get_visible(db, viewer, template_id))
    result = await _run(db, svc.promote(db, tpl, viewer=viewer, domain=body.domain, slot_keys=body.slot_keys,
                                        decisions=body.decisions.to_decisions(), request_id=body.request_id,
                                        note=body.note))
    await publish_events(result.get("events") or [], domain=body.domain, source="template_promote",
                         token=result.get("publish_id"))
    return _public_result(result)


# ── 项目订阅 ──────────────────────────────────────────────────────────────────


@project_router.get("/subscriptions")
async def list_subscriptions(project_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_project_access("readonly"))):
    rows = (await db.execute(sa.select(FormulaTemplateSubscription, FormulaTemplate).join(
        FormulaTemplate, FormulaTemplate.id == FormulaTemplateSubscription.template_id).where(
        FormulaTemplateSubscription.project_id == project_id,
        FormulaTemplateSubscription.is_active == sa.true()))).all()
    return {"items": [{"domain": s.domain, "template_id": str(t.id), "template_name": t.name,
                       "template_version": s.template_version, "current_version": t.version, "pinned": s.pinned,
                       "behind": s.template_version < t.version} for s, t in rows]}


@project_router.post("/subscribe-preview")
async def subscribe_preview(project_id: uuid.UUID, body: SubscribeBody, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_project_access("edit"))):
    tpl = await _call(get_visible(db, await _viewer(db, current_user), body.template_id))
    return await _call(sync.subscribe_preview(db, project_id=project_id, tpl=tpl, domain=body.domain))


@project_router.post("/subscribe")
async def subscribe(project_id: uuid.UUID, body: SubscribeBody, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(require_project_access("edit"))):
    tpl = await _call(get_visible(db, await _viewer(db, current_user), body.template_id))
    result = await _run(db, sync.subscribe(db, project_id=project_id, tpl=tpl, domain=body.domain,
                                           decisions=body.decisions.to_decisions(), user_id=current_user.id))
    return await _emit(result, "template_subscribe")


@project_router.post("/unsubscribe-preview")
async def unsubscribe_preview(project_id: uuid.UUID, body: UnsubscribeBody, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_project_access("edit"))):
    return await _call(sync.unsubscribe_preview(db, project_id=project_id, domain=body.domain, mode=body.mode))


@project_router.post("/unsubscribe")
async def unsubscribe(project_id: uuid.UUID, body: UnsubscribeBody, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_project_access("edit"))):
    result = await _run(db, sync.unsubscribe(db, project_id=project_id, domain=body.domain, mode=body.mode,
                                             decisions=body.decisions.to_decisions(), user_id=current_user.id))
    return await _emit(result, "template_unsubscribe")
