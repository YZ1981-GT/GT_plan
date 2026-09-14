"""A21~A25 复核底稿 API — definitions / review-context / review-sign / review-unlock / export."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
import sqlalchemy as sa
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
from app.services.review_rbac_guard import calc_unresolved_count, check_rbac, check_sign_lock
from app.services.version_trail_service import VersionTrailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["a21-review"])


class ReviewSignRequest(BaseModel):
    project_id: UUID
    wp_code: str
    action: str
    comment: str = ""


class ReviewUnlockRequest(BaseModel):
    project_id: UUID
    wp_code: str
    reason: str


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

    # RBAC 前置校验
    rbac_denied = await check_rbac(db, current_user.id, body.project_id, body.wp_code)
    if rbac_denied:
        raise HTTPException(403, detail="无权签署此级别复核表")

    # Unresolved count 前置校验（仅 pass 签字需要）
    if body.action == "pass":
        count = await calc_unresolved_count(db, wp_id)
        if count > 0:
            raise HTTPException(
                422, detail=f"尚有 {count} 项复核意见未清零，无法签字"
            )

    try:
        # ── 版本链：复核签字前自动快照 ──
        await VersionTrailService.create_snapshot_fire_and_forget(
            db=db,
            project_id=body.project_id,
            workpaper_id=wp_id,
            user_id=current_user.id,
            snapshot_type="review_sign",
            description=f"复核签字: {current_user.username}, action={body.action}",
        )

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
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.post("/workpapers/{wp_id}/review-unlock")
async def review_unlock(
    wp_id: UUID,
    body: ReviewUnlockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """解锁已签字的复核表（仅合伙人可操作）."""
    wp = await db.get(WorkingPaper, wp_id)
    if not wp or wp.project_id != body.project_id:
        raise HTTPException(404, "底稿不存在")

    # 1. 校验 reason 非空
    if not body.reason or not body.reason.strip():
        raise HTTPException(422, detail="解锁必须填写原因")

    # 2. 校验 -sign 记录存在
    sign_item_id = f"{body.wp_code}-sign"
    sign_result = await db.execute(
        sa.text(
            """
            SELECT id, remark FROM checklist_responses
            WHERE project_id = :project_id
              AND item_id = :item_id
              AND conclusion = 'pass'
            LIMIT 1
            """
        ),
        {"project_id": str(body.project_id), "item_id": sign_item_id},
    )
    sign_row = sign_result.first()

    if sign_row is None:
        raise HTTPException(422, detail="该复核表未签字，无需解锁")

    # 3. 校验当前用户 role == signing_partner
    from app.models.staff_models import ProjectAssignment, StaffMember

    staff_stmt = (
        sa.select(StaffMember.id)
        .where(StaffMember.user_id == current_user.id)
        .where(StaffMember.is_deleted == sa.false())
        .limit(1)
    )
    staff_result = await db.execute(staff_stmt)
    staff_id = staff_result.scalar_one_or_none()

    if staff_id is None:
        raise HTTPException(403, detail="仅合伙人可解锁已签字复核表")

    partner_stmt = (
        sa.select(sa.func.count())
        .select_from(ProjectAssignment.__table__)
        .where(ProjectAssignment.project_id == body.project_id)
        .where(ProjectAssignment.staff_id == staff_id)
        .where(ProjectAssignment.role == "signing_partner")
        .where(ProjectAssignment.is_deleted == sa.false())
    )
    partner_result = await db.execute(partner_stmt)
    partner_count = partner_result.scalar() or 0

    if partner_count == 0:
        raise HTTPException(403, detail="仅合伙人可解锁已签字复核表")

    # 4. 提取原签字人 ID
    original_signer_id: str | None = None
    sign_remark_raw = sign_row[1]  # remark column
    if sign_remark_raw:
        try:
            remark_data = json.loads(sign_remark_raw)
            if isinstance(remark_data, dict):
                original_signer_id = remark_data.get("signer_id")
        except (json.JSONDecodeError, TypeError):
            pass

    # 5. 删除 -sign 记录
    sign_record_id = sign_row[0]
    await db.execute(
        sa.text("DELETE FROM checklist_responses WHERE id = :id"),
        {"id": str(sign_record_id)},
    )

    # 6. 创建 -unlock-log 记录
    import uuid as uuid_mod

    unlocked_at = datetime.now(timezone.utc).isoformat()
    unlock_log_remark = json.dumps(
        {
            "unlocked_by": str(current_user.id),
            "unlocked_at": unlocked_at,
            "reason": body.reason.strip(),
            "original_signer_id": original_signer_id,
        },
        ensure_ascii=False,
    )
    unlock_log_item_id = f"{body.wp_code}-unlock-log"

    await db.execute(
        sa.text(
            """
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
            VALUES (:id, :project_id, :wp_id, :item_id, 'unlocked', :remark, :now, :now)
            """
        ),
        {
            "id": str(uuid_mod.uuid4()),
            "project_id": str(body.project_id),
            "wp_id": str(wp_id),
            "item_id": unlock_log_item_id,
            "remark": unlock_log_remark,
            "now": unlocked_at,
        },
    )

    await db.commit()

    return {"success": True, "unlocked_at": unlocked_at}
