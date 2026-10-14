"""附注内容模板 CRUD router。

路径：``/api/projects/{project_id}/note-content-templates/...``
注册：``router_registry/report.py``
"""

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

from app.deps import get_current_user, get_db, require_project_access
from app.services.note_content_template_snapshot import (
    get_template_detail,
    list_templates,
    list_versions,
    save_snapshot,
    snapshot_preview,
    soft_delete_template,
)

router = APIRouter(prefix="/api/projects/{project_id}/note-content-templates")


@router.get("", summary="列表：当前用户可见的附注内容模板")
async def list_templates_endpoint(
    project_id: UUID,
    user=Depends(require_project_access("readonly")),
    db=Depends(get_db),
):
    items = await list_templates(db, project_id=project_id, user=user)
    return {"items": items, "total": len(items)}


@router.get("/{template_id}", summary="详情：模板元数据（不含正文）")
async def get_template_endpoint(
    project_id: UUID,
    template_id: UUID,
    user=Depends(require_project_access("readonly")),
    db=Depends(get_db),
):
    detail = await get_template_detail(db, template_id, project_id=project_id, user=user)
    if not detail:
        raise HTTPException(status_code=404, detail="模板不存在或无权访问")
    return detail


@router.get("/{template_id}/versions", summary="版本列表：不可变版本元数据")
async def list_versions_endpoint(
    project_id: UUID,
    template_id: UUID,
    user=Depends(require_project_access("readonly")),
    db=Depends(get_db),
):
    versions = await list_versions(db, template_id, project_id=project_id, user=user)
    if versions is None:
        raise HTTPException(status_code=404, detail="模板不存在或无权访问")
    return {"items": versions, "total": len(versions)}


@router.post("/snapshot-preview", summary="预检：全套快照摘要（不落库）")
async def snapshot_preview_endpoint(
    project_id: UUID,
    year: int,
    user=Depends(require_project_access("edit")),
    db=Depends(get_db),
):
    try:
        return await snapshot_preview(db, project_id, year)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("", summary="保存：创建不可变版本")
async def save_template_endpoint(
    project_id: UUID,
    body: dict,
    user=Depends(require_project_access("edit")),
    db=Depends(get_db),
):
    try:
        result = await save_snapshot(
            db,
            project_id=project_id,
            year=body.get("year", 0),
            name=body.get("name", ""),
            description=body.get("description"),
            owner_scope=body.get("owner_scope", "personal"),
            snapshot_digest=body.get("snapshot_digest", ""),
            user=user,
        )
        await db.commit()
        return result
    except ValueError as e:
        msg = str(e)
        if "STALE" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=422, detail=msg)


@router.delete("/{template_id}", summary="软删除模板")
async def delete_template_endpoint(
    project_id: UUID,
    template_id: UUID,
    user=Depends(require_project_access("edit")),
    db=Depends(get_db),
):
    deleted = await soft_delete_template(db, template_id, project_id=project_id, user=user)
    if not deleted:
        raise HTTPException(status_code=404, detail="模板不存在或无权删除")
    await db.commit()
    return {"id": str(template_id), "deleted": True}
