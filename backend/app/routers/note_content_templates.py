"""附注内容模板 router。

spec: disclosure-note-doc-upload-and-batch-fill Task 41~45（第二轮复盘 R-03 / R-04 / R-15）

路径：``/api/projects/{project_id}/note-content-templates/...``；注册：``router_registry/report.py``

- 预检 / 保存 / 删除需项目 edit；列表 / 详情 / 版本需 readonly；模板可见性由 service 统一判定，不可见一律 404；
- 请求体走严格 schema（R-03：首版 ``body: dict``，``owner_scope='public'`` 原样落到 service、``year`` 缺省成 0）。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_project_access
from app.models.core import User
from app.models.note_content_template_schemas import SaveContentTemplateRequest, SnapshotPreviewRequest
from app.services.note_content_template_snapshot import (
    TemplateError,
    get_template_detail,
    list_templates,
    list_versions,
    save_snapshot,
    snapshot_preview,
    soft_delete_template,
)

router = APIRouter(prefix="/api/projects/{project_id}/note-content-templates")

_NOT_VISIBLE = {"error_code": "TEMPLATE_NOT_VISIBLE", "message": "模板不存在或无权访问"}


def _http_error(err: TemplateError) -> HTTPException:
    return HTTPException(err.status, {"error_code": err.code, "message": err.message})


@router.get("", summary="列表：当前用户在本项目可见的附注内容模板（分页，只含元数据）")
async def list_templates_endpoint(
    project_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    year: int | None = Query(None, ge=2000, le=2200, description="给定时 last_applied 只看本项目该年度的引用"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await list_templates(db, project_id=project_id, user=current_user, limit=limit, offset=offset, year=year)


@router.post("/snapshot-preview", summary="预检：全套快照质量摘要与 digest（不落库）")
async def snapshot_preview_endpoint(
    project_id: UUID,
    body: SnapshotPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    try:
        return await snapshot_preview(db, project_id, body.year, user=current_user, owner_scope=body.owner_scope)
    except TemplateError as err:
        raise _http_error(err) from err


@router.post("", summary="保存：创建或复用不可变版本")
async def save_template_endpoint(
    project_id: UUID,
    body: SaveContentTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    try:
        result = await save_snapshot(
            db, project_id=project_id, year=body.year, name=body.name, description=body.description,
            owner_scope=body.owner_scope, snapshot_digest=body.snapshot_digest, user=current_user,
        )
    except TemplateError as err:
        await db.rollback()
        raise _http_error(err) from err
    await db.commit()
    return result


@router.get("/{template_id}", summary="详情：模板与当前版本元数据（不含正文）")
async def get_template_endpoint(
    project_id: UUID,
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    detail = await get_template_detail(db, template_id, project_id=project_id, user=current_user)
    if detail is None:
        raise HTTPException(404, _NOT_VISIBLE)
    return detail


@router.get("/{template_id}/versions", summary="版本列表：不可变版本元数据")
async def list_versions_endpoint(
    project_id: UUID,
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    versions = await list_versions(db, template_id, project_id=project_id, user=current_user)
    if versions is None:
        raise HTTPException(404, _NOT_VISIBLE)
    return {"items": versions, "total": len(versions)}


@router.delete("/{template_id}", summary="软删除模板目录（版本与应用记录保留）")
async def delete_template_endpoint(
    project_id: UUID,
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    try:
        deleted = await soft_delete_template(db, template_id, project_id=project_id, user=current_user)
    except TemplateError as err:
        raise _http_error(err) from err
    if not deleted:
        raise HTTPException(404, _NOT_VISIBLE)
    await db.commit()
    return {"id": str(template_id), "deleted": True}
