"""复核流程与独立性签署 API 端点"""

from __future__ import annotations

import io
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.independence_signing_service import IndependenceSigningService
from app.services.review_workflow_service import ReviewWorkflowService

router = APIRouter(prefix="/api/projects/{project_id}/review-workflow", tags=["review-workflow"])
signing_router = APIRouter(prefix="/api/projects/{project_id}/signing", tags=["signing"])
my_signing_router = APIRouter(prefix="/api/my/signing-tasks", tags=["signing"])


# ─── Review Workflow ───


class SaveReviewRequest(BaseModel):
    template_code: str
    items: list[dict]
    opinion: str = ""
    submit: bool = False


class LinkConversationRequest(BaseModel):
    conversation_id: str
    checklist_ref: str


@router.get("/{year}/panel")
async def get_review_panel(
    project_id: UUID,
    year: int,
    role: str = Query(..., description="复核角色: field_lead/manager/partner/quality_reviewer/eqcr"),
    audit_type: str = Query("financial"),
    business_category: str = Query("C"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取复核面板数据"""
    svc = ReviewWorkflowService(db)
    return await svc.get_review_panel(project_id, year, role, audit_type, business_category)


@router.post("/{year}/save")
async def save_review(
    project_id: UUID,
    year: int,
    body: SaveReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """保存复核记录"""
    svc = ReviewWorkflowService(db)
    result = await svc.save_review(
        project_id, year, body.template_code, current_user.id, body.items, body.opinion, body.submit
    )
    await db.commit()
    return result


@router.get("/{year}/completion-checklist")
async def get_completion_checklist(
    project_id: UUID,
    year: int,
    project_type: str = Query("general"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """A17-5 完成核对表"""
    svc = ReviewWorkflowService(db)
    return await svc.get_completion_checklist(project_id, year, project_type)


@router.get("/{year}/archive")
async def export_archive(
    project_id: UUID,
    year: int,
    template_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """导出 A21~A25 归档 Excel"""
    svc = ReviewWorkflowService(db)
    content = await svc.generate_archive_file(project_id, year, template_code)
    filename = f"Review_Archive_{year}.xlsx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/{year}/link-conversation")
async def link_conversation(
    project_id: UUID,
    year: int,
    body: LinkConversationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """将复核对话关联到检查要点"""
    svc = ReviewWorkflowService(db)
    ok = await svc.link_conversation(UUID(body.conversation_id), body.checklist_ref)
    if ok:
        await db.commit()
    return {"success": ok}


@router.post("/{year}/unlink-conversation")
async def unlink_conversation(
    project_id: UUID,
    year: int,
    conversation_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """取消关联"""
    svc = ReviewWorkflowService(db)
    ok = await svc.unlink_conversation(UUID(conversation_id))
    if ok:
        await db.commit()
    return {"success": ok}


@router.get("/{year}/progress")
async def get_review_progress(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取复核阶段进度"""
    svc = ReviewWorkflowService(db)
    return await svc.get_review_progress(project_id, year)


@router.post("/{year}/import")
async def import_review_excel(
    project_id: UUID,
    year: int,
    template_code: str = Query(...),
    reviewer_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """导入已填写的复核 Excel 回写系统"""
    from fastapi import UploadFile, File

    # This endpoint would parse the uploaded Excel and extract checked items
    # For now, return the expected interface
    return {"success": True, "note": "导入功能需配合文件上传使用"}


@router.get("/{year}/export-blank")
async def export_blank_template(
    project_id: UUID,
    year: int,
    template_code: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """导出空白复核模板 Excel（供线下填写）"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    templates = ReviewWorkflowService(db).formulas if hasattr(ReviewWorkflowService, 'formulas') else None
    from app.services.review_workflow_service import _load_templates
    all_templates = _load_templates()["templates"]
    tmpl = all_templates.get(template_code)
    if not tmpl:
        from fastapi import HTTPException
        raise HTTPException(404, f"未找到模板 {template_code}")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = template_code

    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="F4F0FA", end_color="F4F0FA", fill_type="solid")

    ws.append([tmpl["title"]])
    ws[1][0].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(["序号", "检查要点", "是否通过（✓/✗）", "备注"])
    for cell in ws[3]:
        cell.font = header_font
        cell.fill = header_fill

    for item in tmpl["items"]:
        ws.append([item["seq"], item["content"], "", ""])

    ws.append([])
    ws.append(["复核意见:", ""])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"{template_code}_blank.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─── Independence Signing ───


@signing_router.post("/{year}/initiate")
async def initiate_signing(
    project_id: UUID,
    year: int,
    template_code: str = Query("A17-7"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """为项目成员创建签署任务"""
    svc = IndependenceSigningService(db)
    if template_code == "A17-7A":
        result = await svc.initiate_signing_for_committee(project_id)
    else:
        result = await svc.initiate_signing(project_id, template_code)
    await db.commit()
    return result


@signing_router.post("/{year}/sign")
async def sign(
    project_id: UUID,
    year: int,
    user_id: str = Query(...),
    template_code: str = Query("A17-7"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """成员电子签署"""
    svc = IndependenceSigningService(db)
    result = await svc.sign(project_id, UUID(user_id), template_code)
    if result.get("success"):
        await db.commit()
    return result


@signing_router.get("/{year}/progress")
async def get_signing_progress(
    project_id: UUID,
    year: int,
    template_code: str = Query("A17-7"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取签署进度"""
    svc = IndependenceSigningService(db)
    return await svc.get_signing_progress(project_id, template_code)


@my_signing_router.get("")
async def get_my_signing_tasks(
    user_id: str = Query(..., description="当前用户ID"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """获取当前用户待签署任务"""
    svc = IndependenceSigningService(db)
    return await svc.get_my_pending_tasks(UUID(user_id))
