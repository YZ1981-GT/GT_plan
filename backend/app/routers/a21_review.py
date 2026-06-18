"""A21~A25 复核底稿 API — definitions / review-context / review-sign / export."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper
from app.services.a21_a25_version_selector import (
    get_applicable_review_templates,
    resolve_review_wp_code,
)
from app.services.a21_xlsx_exporter import export_review_checklist_xlsx
from app.services.review_checklist_service import (
    get_prefill_suggestions,
    get_review_context,
    get_review_definition_for_wp,
    get_review_sign_status_batch,
    save_review_sign,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["a21-review"])


class ReviewSignRequest(BaseModel):
    project_id: UUID
    wp_code: str
    action: str
    comment: str = ""


@router.get("/projects/{project_id}/review-context")
async def review_context(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await get_review_context(db, project_id)


@router.get("/projects/{project_id}/a21/applicable-review-templates")
async def applicable_review_templates(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await get_applicable_review_templates(db, project_id)


@router.get("/projects/{project_id}/a21/review-definitions")
async def review_definitions(
    project_id: UUID,
    wp_code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    tpl = await get_review_definition_for_wp(db, project_id, wp_code)
    if not tpl:
        raise HTTPException(404, f"未找到复核定义: {wp_code}")
    ctx = await get_review_context(db, project_id)
    return {"template": tpl, "context": ctx}


@router.get("/projects/{project_id}/a21/prefill-suggestions")
async def prefill_suggestions(
    project_id: UUID,
    wp_code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await get_prefill_suggestions(db, project_id, wp_code)


@router.get("/projects/{project_id}/a21/resolve-wp-code")
async def resolve_wp_code(
    project_id: UUID,
    ref: str = Query(..., description="程序表 ref_index，如 A21 或 A24"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """将父码 A21/A22… 解析为当前项目适用的子码（如 A21-1）。"""
    templates = await get_applicable_review_templates(db, project_id)
    return resolve_review_wp_code(templates, ref)


@router.get("/projects/{project_id}/a21/review-sign-status")
async def review_sign_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await get_review_sign_status_batch(db, project_id)


@router.post("/workpapers/{wp_id}/review-sign")
async def review_sign(
    wp_id: UUID,
    body: ReviewSignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wp = await db.get(WorkingPaper, wp_id)
    if not wp or wp.project_id != body.project_id:
        raise HTTPException(404, "底稿不存在")
    try:
        result = await save_review_sign(
            db,
            body.project_id,
            wp_id,
            body.wp_code,
            body.action,
            body.comment,
            current_user.id,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/workpapers/{wp_id}/export-review-xlsx")
async def export_review_xlsx(
    wp_id: UUID,
    project_id: UUID = Query(...),
    wp_code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    wp = await db.get(WorkingPaper, wp_id)
    if not wp or wp.project_id != project_id:
        raise HTTPException(404, "底稿不存在")
    try:
        data, filename = await export_review_checklist_xlsx(
            db, project_id, wp_id, wp_code
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        logger.exception("export_review_xlsx failed")
        raise HTTPException(500, f"导出失败: {e}") from e

    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        },
    )
