"""共享配置模板 API

- GET    /shared-config/templates          查询可用模板列表
- POST   /shared-config/templates          保存为模板
- GET    /shared-config/templates/{id}     模板详情
- PUT    /shared-config/templates/{id}     更新模板
- DELETE /shared-config/templates/{id}     删除模板
- POST   /shared-config/apply              引用模板到项目
- GET    /shared-config/references/{pid}   项目引用历史

鉴权（spec formula-global-settings-sync R14.1，见 ``shared_config_access``）：创建事务所模板仅 admin、
集团模板需所属项目 edit；修改 / 删除仅所有者或 admin；详情按可见性；引用与引用历史需目标项目权限。
``formula_config`` 类型下线（R14.2，改用公式模板）。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user, require_project_access
from app.models.core import User
from app.models.shared_config_schemas import (
    SharedConfigCreate, SharedConfigUpdate, SharedConfigResponse,
    SharedConfigDetail, ApplyTemplateRequest, ApplyTemplateResponse,
)
from app.services import shared_config_access as access
from app.services.shared_config_service import SharedConfigService

router = APIRouter(prefix="/api/shared-config", tags=["shared-config"])


async def _visible(svc: SharedConfigService, db: AsyncSession, user: User, template_id: UUID):
    tpl = await svc.get_template(template_id)
    if not await access.can_view(db, user, tpl):
        raise HTTPException(status_code=404, detail="模板不存在")
    return tpl


@router.get("/templates")
async def list_templates(
    config_type: str = Query(..., description="配置类型"),
    project_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询当前用户可用的模板列表"""
    if config_type in access.RETIRED_TYPES:
        return []
    if project_id is not None:  # 按项目判集团可见性：须是该项目成员
        await assert_project_permission(db, current_user, project_id, "readonly")
    svc = SharedConfigService(db)
    # 列表与详情 / 版本同一可见性口径（R14.1）：取全部未删除模板，经 access.can_view 过滤，
    # 不再用旧的 list_available_templates（它只认直接上级、不传 project_id 时漏掉集团模板）。
    visible = await access.list_visible(db, current_user, config_type, await svc.all_templates(config_type))
    return [SharedConfigResponse.model_validate(t) for t in visible]


@router.post("/templates")
async def save_template(
    body: SharedConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存当前配置为共享模板"""
    await access.check_create(db, current_user, owner_type=body.owner_type, owner_project_id=body.owner_project_id,
                              config_type=body.config_type)
    svc = SharedConfigService(db)
    tpl = await svc.save_as_template(
        name=body.name,
        config_type=body.config_type,
        config_data=body.config_data,
        owner_type=body.owner_type,
        owner_user_id=current_user.id if body.owner_type == "personal" else None,
        owner_project_id=body.owner_project_id if body.owner_type == "group" else None,
        description=body.description,
        applicable_standard=body.applicable_standard,
        is_public=body.is_public,
        allowed_project_ids=body.allowed_project_ids,
    )
    await db.commit()
    return SharedConfigResponse.model_validate(tpl)


@router.get("/templates/{template_id}")
async def get_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取模板详情（含配置数据）"""
    tpl = await _visible(SharedConfigService(db), db, current_user, template_id)
    return SharedConfigDetail.model_validate(tpl)


@router.put("/templates/{template_id}")
async def update_template(
    template_id: UUID,
    body: SharedConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新模板"""
    tpl = await _visible(SharedConfigService(db), db, current_user, template_id)
    await access.check_manage(db, current_user, tpl)
    if body.name is not None:
        tpl.name = body.name
    if body.description is not None:
        tpl.description = body.description
    if body.config_data is not None:
        tpl.config_data = body.config_data
        tpl.config_version = (tpl.config_version or 1) + 1
    if body.applicable_standard is not None:
        tpl.applicable_standard = body.applicable_standard
    if body.is_public is not None:
        tpl.is_public = body.is_public
    if body.allowed_project_ids is not None:
        tpl.allowed_project_ids = [str(pid) for pid in body.allowed_project_ids]
    await db.commit()
    await db.refresh(tpl)  # updated_at 由库端 onupdate 生成，提交后过期；异步会话里懒加载会 MissingGreenlet
    return SharedConfigResponse.model_validate(tpl)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除模板"""
    svc = SharedConfigService(db)
    await access.check_manage(db, current_user, await _visible(svc, db, current_user, template_id))
    try:
        ok = await svc.delete_template(template_id, current_user.id)
        await db.commit()
        return {"deleted": ok}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/apply")
async def apply_template(
    body: ApplyTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """引用模板到项目"""
    await assert_project_permission(db, current_user, body.project_id, "edit")
    svc = SharedConfigService(db)
    access.check_not_retired((await _visible(svc, db, current_user, body.template_id)).config_type)
    try:
        result = await svc.apply_template(
            template_id=body.template_id,
            project_id=body.project_id,
            user_id=current_user.id,
        )
        await db.commit()
        return ApplyTemplateResponse(
            success=True,
            message=f"已引用模板「{result['template_name']}」v{result['template_version']}",
            config_type=result["config_type"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/references/{project_id}")
async def list_references(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询项目的模板引用历史"""
    svc = SharedConfigService(db)
    refs = await svc.list_references(project_id)
    return refs
