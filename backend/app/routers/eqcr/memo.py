"""EQCR 备忘录端点"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.services.eqcr_service import EqcrService

from .schemas import EqcrMemoSaveRequest

router = APIRouter()


@router.post("/projects/{project_id}/memo")
async def generate_eqcr_memo(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成 EQCR 备忘录（需求 9）。"""
    from app.services.eqcr_memo_service import EqcrMemoService

    svc = EqcrMemoService(db)
    try:
        memo = await svc.generate_memo(project_id, current_user.id)
        await svc.save_memo(project_id, memo["sections"])
        await db.commit()
        return memo
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/memo/preview")
async def preview_eqcr_memo(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """预览已保存的 EQCR 备忘录。"""
    proj_q = select(Project).where(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    )
    proj = (await db.execute(proj_q)).scalar_one_or_none()
    if proj is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    wizard = proj.wizard_state or {}
    memo = wizard.get("eqcr_memo")
    if not memo:
        raise HTTPException(status_code=404, detail="备忘录尚未生成")

    return {
        "project_id": str(project_id),
        "sections": memo.get("sections", {}),
        "status": memo.get("status", "draft"),
        "updated_at": memo.get("updated_at"),
        "finalized_at": memo.get("finalized_at"),
    }


@router.put("/projects/{project_id}/memo")
async def save_eqcr_memo(
    project_id: UUID,
    payload: EqcrMemoSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存编辑后的 EQCR 备忘录。"""
    from app.services.eqcr_memo_service import EqcrMemoService

    svc = EqcrMemoService(db)
    try:
        result = await svc.save_memo(project_id, payload.sections)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/memo/finalize")
async def finalize_eqcr_memo(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """定稿 EQCR 备忘录（需求 9）。"""
    from app.services.eqcr_memo_service import EqcrMemoService

    svc_eqcr = EqcrService(db)
    is_eqcr = await svc_eqcr._is_user_eqcr_on(current_user.id, project_id)
    if not is_eqcr:
        raise HTTPException(status_code=403, detail="非本项目 EQCR，无权定稿")

    svc = EqcrMemoService(db)
    try:
        result = await svc.finalize_memo(project_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/memo/export")
async def export_eqcr_memo(
    project_id: UUID,
    format: str = "docx",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出 EQCR 备忘录为 Word 文档 [R7-S3-04 Task 23]。

    参数：
        format: 'docx'（默认）
    返回：
        Word 文件字节流（application/vnd.openxmlformats-officedocument.wordprocessingml.document）
    """
    from fastapi.responses import Response
    from app.services.eqcr_memo_service import EqcrMemoService

    svc = EqcrMemoService(db)
    try:
        memo_data = await svc.generate_memo(project_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    sections = memo_data.get("sections") or {}
    if not sections:
        raise HTTPException(status_code=404, detail="备忘录尚未生成")

    # 生成 Word 文档
    from app.services.eqcr_memo_service import build_memo_docx_bytes
    docx_bytes = build_memo_docx_bytes(sections, project_name=memo_data.get("project_name", ""))

    filename = f"EQCR备忘录_{memo_data.get('project_name', project_id)}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
