"""底稿证据链路由

Sprint 6 Task 6.2:
  GET  /                获取底稿所有证据链接
  POST /link            创建证据链接（单元格→附件）
  DELETE /{link_id}     删除证据链接
  POST /batch-link      批量关联（区域→多附件）
  GET  /sufficiency     证据充分性检查
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.wp_evidence_service import WpEvidenceService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/evidence",
    tags=["workpaper-evidence"],
)


# ─── Request Models ───────────────────────────────────────────────────────────


class CreateLinkRequest(BaseModel):
    attachment_id: str
    sheet_name: str | None = None
    cell_ref: str | None = None
    page_ref: str | None = None
    evidence_type: str | None = None
    check_conclusion: str | None = None
    created_by: str = Field(default="00000000-0000-0000-0000-000000000000")


class BatchLinkItem(BaseModel):
    attachment_id: str
    sheet_name: str | None = None
    cell_ref: str | None = None
    page_ref: str | None = None
    evidence_type: str | None = None
    check_conclusion: str | None = None


class BatchLinkRequest(BaseModel):
    links: list[BatchLinkItem]
    created_by: str = Field(default="00000000-0000-0000-0000-000000000000")


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("")
async def get_evidence_links(
    project_id: str,
    wp_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取底稿所有证据链接"""
    svc = WpEvidenceService(db)
    items = await svc.list_links(UUID(wp_id))
    return {"items": items, "total": len(items)}


@router.post("/link")
async def create_evidence_link(
    project_id: str,
    wp_id: str,
    body: CreateLinkRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建证据链接（单元格→附件）"""
    svc = WpEvidenceService(db)
    result = await svc.create_link(
        wp_id=UUID(wp_id),
        attachment_id=UUID(body.attachment_id),
        created_by=UUID(body.created_by),
        sheet_name=body.sheet_name,
        cell_ref=body.cell_ref,
        page_ref=body.page_ref,
        evidence_type=body.evidence_type,
        check_conclusion=body.check_conclusion,
    )
    await db.commit()
    return result


@router.delete("/{link_id}")
async def delete_evidence_link(
    project_id: str,
    wp_id: str,
    link_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除证据链接"""
    svc = WpEvidenceService(db)
    ok = await svc.delete_link(UUID(link_id))
    if not ok:
        raise HTTPException(status_code=404, detail="证据链接不存在")
    await db.commit()
    return {"ok": True}


@router.post("/batch-link")
async def batch_link_evidence(
    project_id: str,
    wp_id: str,
    body: BatchLinkRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量关联（区域→多附件）"""
    svc = WpEvidenceService(db)
    results = await svc.batch_link(
        wp_id=UUID(wp_id),
        created_by=UUID(body.created_by),
        links=[item.model_dump() for item in body.links],
    )
    await db.commit()
    return {"items": results, "total": len(results)}


@router.get("/sufficiency")
async def check_evidence_sufficiency(
    project_id: str,
    wp_id: str,
    db: AsyncSession = Depends(get_db),
):
    """证据充分性检查"""
    svc = WpEvidenceService(db)
    return await svc.check_sufficiency(UUID(wp_id))
