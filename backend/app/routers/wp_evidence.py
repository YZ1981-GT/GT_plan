"""底稿证据链路由

  GET  /                获取底稿证据链接（含附件元数据，可按表页 / 单元格过滤）
  POST /upload          上传新证据并关联（整稿或行级，spec attachment-evidence-intake 需求 1）
  POST /link            把本底稿已有附件链接到表页 / 单元格
  DELETE /{link_id}     删除证据链接（不删附件）
  POST /batch-link      批量链接
  GET  /sufficiency     证据充分性检查

路由级 readonly 保证项目成员；写端点再挂 edit；注册时附加的 ``dedicated_wp_gate`` 按方法判底稿内容读写
（编制人可写，复核人只读，见 design §5）。底稿必须属于路径项目，否则 404（改造前不校，任何项目的成员
能借自己项目的路径改别的项目的底稿证据）；``created_by`` 取当前用户，不再采用请求体（原缺省全零）。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.attachment_destructive_guard import assert_project_writable
from app.services.wp_evidence_service import WpEvidenceService
from app.services.workpaper_evidence_intake import (
    build_position,
    create_evidence,
    load_workpaper,
    read_upload_limited,
    resolve_evidence_type,
    validate_evidence_type,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/evidence",
    tags=["workpaper-evidence"],
    dependencies=[Depends(require_project_access("readonly"))],
)


# ─── Request Models ───────────────────────────────────────────────────────────


class CreateLinkRequest(BaseModel):
    attachment_id: UUID
    sheet_name: str | None = None
    cell_ref: str | None = None
    page_ref: str | None = None
    evidence_type: str | None = None
    check_conclusion: str | None = None


class BatchLinkItem(BaseModel):
    attachment_id: UUID
    sheet_name: str | None = None
    cell_ref: str | None = None
    page_ref: str | None = None
    evidence_type: str | None = None
    check_conclusion: str | None = None


class BatchLinkRequest(BaseModel):
    links: list[BatchLinkItem]


async def _writable_wp(db: AsyncSession, project_id: UUID, wp_id: UUID, user: User):
    wp = await load_workpaper(db, wp_id, project_id=project_id)
    await assert_project_writable(db, wp.project_id, user)
    return wp


async def _validated_link_fields(item: CreateLinkRequest | BatchLinkItem) -> dict:
    position = build_position(item.sheet_name, item.cell_ref, item.page_ref)
    return {
        "attachment_id": item.attachment_id,
        "sheet_name": position.sheet_name,
        "cell_ref": position.cell_ref,
        "page_ref": position.page_ref,
        "evidence_type": validate_evidence_type(item.evidence_type),
        "check_conclusion": item.check_conclusion,
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("")
async def get_evidence_links(
    project_id: UUID,
    wp_id: UUID,
    sheet_name: str | None = Query(None),
    cell_ref: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """获取底稿证据链接（附件已软删的不返回）。"""
    wp = await load_workpaper(db, wp_id, project_id=project_id)
    items = await WpEvidenceService(db).list_links(wp.id, sheet_name=sheet_name, cell_ref=cell_ref)
    return {"items": items, "total": len(items)}


@router.post("/upload")
async def upload_evidence(
    project_id: UUID,
    wp_id: UUID,
    file: UploadFile = File(...),
    evidence_type: str | None = Form(None),
    sheet_name: str | None = Form(None),
    cell_ref: str | None = Form(None),
    page_ref: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """上传新证据：不带位置 ⇒ 整稿关联；带表页或单元格 ⇒ 只写行级证据链接（需求 1.1）。"""
    wp = await _writable_wp(db, project_id, wp_id, current_user)
    position = build_position(sheet_name, cell_ref, page_ref)
    content = await read_upload_limited(file)
    result = await create_evidence(
        db, wp=wp, file_name=file.filename or "attachment.bin", content=content,
        evidence_type=resolve_evidence_type(evidence_type, wp.wp_code), user=current_user, position=position,
    )
    await db.commit()
    try:
        from app.services.event_bus import event_bus

        event_bus.broadcast_raw(
            event_type="attachment.uploaded",
            extra={"project_id": str(project_id), "attachment_id": result["attachment"]["id"], "wp_id": str(wp_id)},
        )
    except Exception:  # noqa: BLE001 — SSE 失败不阻断上传
        logger.debug("attachment.uploaded broadcast skipped", exc_info=True)
    return result


@router.post("/link")
async def create_evidence_link(
    project_id: UUID,
    wp_id: UUID,
    body: CreateLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """把本底稿已有附件链接到表页 / 单元格（附件不在本底稿 ⇒ 404，需求 3.2）。"""
    wp = await _writable_wp(db, project_id, wp_id, current_user)
    fields = await _validated_link_fields(body)
    svc = WpEvidenceService(db)
    await svc.assert_attachments_in_wp(wp, [fields["attachment_id"]])
    result = await svc.create_link(wp_id=wp.id, created_by=current_user.id, **fields)
    await db.commit()
    return result


@router.delete("/{link_id}")
async def delete_evidence_link(
    project_id: UUID,
    wp_id: UUID,
    link_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """删除证据链接（链接须属路径底稿；不删附件）。"""
    wp = await _writable_wp(db, project_id, wp_id, current_user)
    ok = await WpEvidenceService(db).delete_link(link_id, wp_id=wp.id)
    if not ok:
        raise HTTPException(status_code=404, detail="证据链接不存在")
    await db.commit()
    return {"ok": True}


@router.post("/batch-link")
async def batch_link_evidence(
    project_id: UUID,
    wp_id: UUID,
    body: BatchLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """批量链接：任一附件不在本底稿或字段不合法 ⇒ 整批不写。"""
    wp = await _writable_wp(db, project_id, wp_id, current_user)
    items = [await _validated_link_fields(item) for item in body.links]
    svc = WpEvidenceService(db)
    await svc.assert_attachments_in_wp(wp, [item["attachment_id"] for item in items])
    results = await svc.batch_link(wp_id=wp.id, created_by=current_user.id, links=items)
    await db.commit()
    return {"items": results, "total": len(results)}


@router.get("/sufficiency")
async def check_evidence_sufficiency(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """证据充分性检查"""
    wp = await load_workpaper(db, wp_id, project_id=project_id)
    return await WpEvidenceService(db).check_sufficiency(wp.id)
