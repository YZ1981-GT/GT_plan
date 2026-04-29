"""底稿管理 API 路由

- GET    /api/projects/{id}/working-papers          — 底稿列表
- GET    /api/projects/{id}/working-papers/{wp_id}   — 底稿详情
- GET    /api/projects/{id}/working-papers/{wp_id}/download — 下载
- POST   /api/projects/{id}/working-papers/{wp_id}/upload   — 上传
- PUT    /api/projects/{id}/working-papers/{wp_id}/status   — 更新状态
- PUT    /api/projects/{id}/working-papers/{wp_id}/assign   — 分配
- POST   /api/projects/{id}/working-papers/{wp_id}/prefill  — 预填充
- POST   /api/projects/{id}/working-papers/{wp_id}/parse    — 解析回写
- GET    /api/projects/{id}/wp-index                 — 底稿索引列表
- GET    /api/projects/{id}/wp-cross-refs            — 交叉索引

Validates: Requirements 6.1-7.5
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.config import settings
from app.core.database import get_db
from app.deps import require_project_access
from app.models.ai_models import AIConfirmationStatus, AIContent
from app.models.core import User
from app.models.phase10_schemas import DownloadPackRequest
from app.services.feature_flags import get_feature_maturity, is_enabled
from app.services.wopi_service import WOPIHostService
from app.services.working_paper_service import WorkingPaperService
from app.services.wp_download_service import WpDownloadService, WpUploadService
from app.models.workpaper_models import WpIndex, WpCrossRef, WorkingPaper, WpFileStatus

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["working-papers"],
)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class UploadRequest(BaseModel):
    recorded_version: int


class StatusUpdateRequest(BaseModel):
    status: str


class AssignRequest(BaseModel):
    assigned_to: UUID | None = None
    reviewer: UUID | None = None


class ReviewStatusRequest(BaseModel):
    review_status: str
    reason: str | None = None  # 退回时必填


# ---------------------------------------------------------------------------
# Working paper endpoints
# ---------------------------------------------------------------------------

@router.get("/working-papers")
async def list_workpapers(
    project_id: UUID,
    audit_cycle: str | None = None,
    status: str | None = None,
    assigned_to: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿列表（支持筛选，需项目成员权限）。自动按用户 scope_cycles 过滤。"""
    # 获取用户的循环范围限制
    scope_cycles = None
    if current_user.role.value not in ("admin", "partner"):
        from app.models.core import ProjectUser
        pu = (await db.execute(
            sa.select(ProjectUser.scope_cycles).where(
                ProjectUser.project_id == project_id,
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False,
            )
        )).scalar()
        if pu and isinstance(pu, str) and pu.strip():
            scope_cycles = [c.strip() for c in pu.split(",") if c.strip()]

    svc = WorkingPaperService()
    return await svc.list_workpapers(
        db=db,
        project_id=project_id,
        audit_cycle=audit_cycle,
        status=status,
        assigned_to=assigned_to,
        scope_cycles=scope_cycles,
    )


@router.post("/working-papers/download-pack")
async def download_workpaper_pack(
    project_id: UUID,
    body: DownloadPackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    svc = WpDownloadService()
    try:
        buf = await svc.download_pack(
            db=db,
            project_id=project_id,
            wp_ids=body.wp_ids,
            include_prefill=body.include_prefill,
        )
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=workpapers.zip"},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/working-papers/{wp_id}")
async def get_workpaper(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿详情（需项目成员权限）"""
    svc = WorkingPaperService()
    detail = await svc.get_workpaper(db=db, wp_id=wp_id, project_id=project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    return detail


@router.get("/working-papers/{wp_id}/online-session")
async def get_online_edit_session(
    project_id: UUID,
    wp_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """获取在线编辑会话配置。

    在线编辑是优先方案；当功能开关关闭或服务未部署时，前端再降级到离线模式。
    """
    wp_result = await db.execute(
        sa.select(WorkingPaper.id).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    if wp_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    maturity = get_feature_maturity().get("online_editing", "pilot")
    enabled = is_enabled("online_editing", project_id)
    if not enabled:
        return {
            "enabled": False,
            "maturity": maturity,
            "preferred_mode": "offline",
            "wopi_src": None,
            "access_token": None,
            "editor_base_url": None,
        }

    access_token = WOPIHostService.generate_access_token(
        user_id=current_user.id,
        project_id=project_id,
        file_id=wp_id,
    )
    wopi_base_url = settings.WOPI_BASE_URL.rstrip("/")
    wopi_src = f"{wopi_base_url}/files/{wp_id}?access_token={access_token}"

    # 构造完整的 ONLYOFFICE 编辑器 URL
    onlyoffice_url = getattr(settings, "ONLYOFFICE_URL", "http://localhost:8080").rstrip("/")
    editor_url = f"{onlyoffice_url}/hosting/wopi/cell?WOPISrc={wopi_src}"

    return {
        "enabled": True,
        "maturity": maturity,
        "preferred_mode": "online",
        "wopi_src": wopi_src,
        "access_token": access_token,
        "editor_url": editor_url,
        "editor_base_url": str(request.base_url).rstrip("/"),
        "onlyoffice_url": onlyoffice_url,
    }


@router.get("/working-papers/{wp_id}/download")
async def download_workpaper(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """下载底稿（需项目成员权限）"""
    svc = WpDownloadService()
    try:
        info = await svc.download_single(db=db, project_id=project_id, wp_id=wp_id)
        from pathlib import Path

        file_path = Path(info["file_path"])
        return StreamingResponse(
            open(file_path, "rb"),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{info["file_name"]}"',
                "X-WP-Version": str(info["file_version"]),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/working-papers/{wp_id}/upload")
async def upload_workpaper(
    project_id: UUID,
    wp_id: UUID,
    data: UploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """上传离线编辑的底稿"""
    svc = WorkingPaperService()
    try:
        result = await svc.upload_offline_edit(
            db=db, wp_id=wp_id, recorded_version=data.recorded_version, project_id=project_id,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/working-papers/{wp_id}/upload-file")
async def upload_workpaper_file(
    project_id: UUID,
    wp_id: UUID,
    file: UploadFile = File(...),
    uploaded_version: int = Query(...),
    force_overwrite: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """上传离线编辑后的底稿文件（正式主链路）。"""
    svc = WpUploadService()
    content = await file.read()
    try:
        result = await svc.upload_file(
            db=db,
            project_id=project_id,
            wp_id=wp_id,
            file_content=content,
            uploaded_version=uploaded_version,
            force_overwrite=force_overwrite,
        )
        if result.get("status") == "conflict":
            raise HTTPException(status_code=409, detail=result)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/working-papers/{wp_id}/status")
async def update_status(
    project_id: UUID,
    wp_id: UUID,
    data: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """更新底稿编制生命周期状态

    编制状态流转由 WorkingPaperService.update_status 严格校验。
    提交复核请使用 POST /submit-review 专用端点（含4项门禁）。
    """
    svc = WorkingPaperService()
    try:
        result = await svc.update_status(db=db, wp_id=wp_id, new_status=data.status, project_id=project_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/working-papers/{wp_id}/assign")
async def assign_workpaper(
    project_id: UUID,
    wp_id: UUID,
    data: AssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """分配编制人/复核人（需 review 权限）"""
    svc = WorkingPaperService()
    try:
        result = await svc.assign_workpaper(
            db=db, wp_id=wp_id, project_id=project_id,
            assigned_to=data.assigned_to,
            reviewer=data.reviewer,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/working-papers/{wp_id}/submit-review")
async def submit_review(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """专用提交复核端点 — 统一校验 5 项门禁后流转复核状态

    门禁：1.复核人已分配 2.QC阻断=0 3.未解决批注=0 4.AI未确认=0 5.open复核意见已回复
    全部通过后：
      - 编制状态 → under_review
      - 复核状态 → pending_level1
    """
    wp_result = await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    wp = wp_result.scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # 只有 edit_complete 或 revision_required→edit_complete 后才能提交
    if wp.status != WpFileStatus.edit_complete:
        current_s = wp.status.value if wp.status else "unknown"
        raise HTTPException(
            status_code=400,
            detail=f"当前编制状态 {current_s} 不允许提交复核，需先完成编制（edit_complete）",
        )

    # ── Phase 14: 统一门禁引擎评估 ──
    try:
        from app.services.gate_engine import gate_engine as _gate_engine
        gate_result = await _gate_engine.evaluate(
            db=db,
            gate_type="submit_review",
            project_id=project_id,
            wp_id=wp_id,
            actor_id=current_user.id,
            context={"wp_status": wp.status, "year": getattr(wp, 'year', None)},
        )
        if gate_result.decision == "block":
            return {
                "status": "blocked",
                "blocking_reasons": [
                    f"[{h.rule_code}] {h.message}" for h in gate_result.hit_rules
                    if h.severity == "blocking"
                ],
                "hit_rules": [
                    {
                        "rule_code": h.rule_code,
                        "error_code": h.error_code,
                        "severity": h.severity,
                        "message": h.message,
                        "location": h.location,
                        "suggested_action": h.suggested_action,
                    }
                    for h in gate_result.hit_rules
                ],
                "can_submit": False,
                "trace_id": gate_result.trace_id,
            }
    except Exception as _gate_err:
        import logging
        logging.getLogger(__name__).warning(f"[GATE] submit_review gate eval failed: {_gate_err}")
        # 门禁引擎故障不阻断，降级走原有门禁逻辑

    # ── Phase 14: SoD 职责分离校验 ──
    try:
        from app.services.sod_guard_service import sod_guard_service as _sod_svc
        sod_result = await _sod_svc.check(
            db=db,
            project_id=project_id,
            wp_id=wp_id,
            actor_id=current_user.id,
            target_role="reviewer",
        )
        if not sod_result.allowed:
            raise HTTPException(status_code=403, detail={
                "error_code": "SOD_CONFLICT_DETECTED",
                "message": sod_result.conflict_type,
                "policy_code": sod_result.policy_code,
                "trace_id": sod_result.trace_id,
            })
    except HTTPException:
        raise
    except Exception as _sod_err:
        import logging
        logging.getLogger(__name__).warning(f"[SOD] submit_review sod check failed: {_sod_err}")

    blocking_reasons = []

    # 门禁 1：复核人已分配
    if not wp.reviewer:
        blocking_reasons.append("复核人未分配")

    # 门禁 2：阻断级 QC 通过
    from app.models.workpaper_models import WpQcResult
    qc_result = await db.execute(
        sa.select(WpQcResult).where(WpQcResult.working_paper_id == wp_id)
        .order_by(WpQcResult.check_timestamp.desc()).limit(1)
    )
    qc = qc_result.scalar_one_or_none()
    if qc is None:
        blocking_reasons.append("未执行质量自检")
    elif qc.blocking_count > 0:
        blocking_reasons.append(f"存在 {qc.blocking_count} 个阻断级 QC 问题")

    # 门禁 3：无未解决复核意见
    try:
        from app.models.phase10_models import CellAnnotation
        ann_result = await db.execute(
            sa.select(sa.func.count()).select_from(CellAnnotation).where(
                CellAnnotation.project_id == project_id,
                CellAnnotation.object_type == "workpaper",
                CellAnnotation.object_id == wp_id,
                CellAnnotation.status != "resolved",
                CellAnnotation.is_deleted == sa.false(),
            )
        )
        unresolved = ann_result.scalar() or 0
        if unresolved > 0:
            blocking_reasons.append(f"{unresolved} 条未解决复核意见")
    except Exception:
        pass

    # 门禁 4：无未确认 AI 内容
    ai_pending_result = await db.execute(
        sa.select(sa.func.count()).select_from(AIContent).where(
            AIContent.project_id == project_id,
            AIContent.workpaper_id == wp_id,
            AIContent.confirmation_status == AIConfirmationStatus.pending,
            AIContent.is_deleted == sa.false(),
        )
    )
    unconfirmed_ai_count = ai_pending_result.scalar() or 0
    if unconfirmed_ai_count > 0:
        blocking_reasons.append(f"{unconfirmed_ai_count} 项未确认的 AI 生成内容")

    # 门禁 5：所有 open 状态的复核意见必须已被 replied
    from app.models.workpaper_models import ReviewRecord, ReviewCommentStatus
    open_unreplied = await db.execute(
        sa.select(sa.func.count()).select_from(ReviewRecord).where(
            ReviewRecord.working_paper_id == wp_id,
            ReviewRecord.status == ReviewCommentStatus.open,
            ReviewRecord.is_deleted == sa.false(),
        )
    )
    unreplied_count = open_unreplied.scalar() or 0
    if unreplied_count > 0:
        blocking_reasons.append(f"{unreplied_count} 条复核意见未回复（状态仍为 open）")

    if blocking_reasons:
        return {
            "status": "blocked",
            "blocking_reasons": blocking_reasons,
            "can_submit": False,
        }

    # 全部通过 → 流转复核状态
    svc = WorkingPaperService()
    try:
        result = await svc.update_review_status(
            db=db, wp_id=wp_id, new_review_status="pending_level1", project_id=project_id,
        )
        await db.commit()

        # 自动同步程序状态（底稿提交复核→程序标记completed）
        try:
            from app.models.procedure_models import ProcedureInstance
            wp_result = await db.execute(
                sa.select(WpIndex.wp_code).where(WpIndex.id == (
                    sa.select(WorkingPaper.wp_index_id).where(WorkingPaper.id == wp_id).scalar_subquery()
                ))
            )
            wp_code_row = wp_result.scalar_one_or_none()
            if wp_code_row:
                await db.execute(
                    sa.update(ProcedureInstance).where(
                        ProcedureInstance.project_id == project_id,
                        ProcedureInstance.wp_code == wp_code_row,
                        ProcedureInstance.is_deleted == sa.false(),
                    ).values(execution_status="completed")
                )
                await db.commit()
        except Exception:
            pass  # 程序联动失败不阻断提交

        return {
            "status": "submitted",
            "can_submit": True,
            "blocking_reasons": [],
            "wp_status": result.get("status"),
            "review_status": result.get("review_status"),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/working-papers/{wp_id}/review-status")
async def update_review_status(
    project_id: UUID,
    wp_id: UUID,
    data: ReviewStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """更新底稿复核任务状态（需 review 权限）

    复核人操作：
      pending_level1 → level1_in_progress → level1_passed/level1_rejected
      pending_level2 → level2_in_progress → level2_passed/level2_rejected
    """
    svc = WorkingPaperService()
    try:
        result = await svc.update_review_status(
            db=db, wp_id=wp_id, new_review_status=data.review_status,
            project_id=project_id, reason=data.reason,
            rejected_by_id=current_user.id,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/working-papers/{wp_id}/prefill")
async def prefill_workpaper(
    project_id: UUID,
    wp_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """手动触发预填充（需编辑权限）— 真正打开 .xlsx 扫描公式并写入"""
    from app.services.prefill_engine import prefill_workpaper_real
    result = await prefill_workpaper_real(db=db, project_id=project_id, year=year, wp_id=wp_id)
    await db.commit()
    return result


@router.post("/working-papers/{wp_id}/parse")
async def parse_workpaper(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """手动触发解析回写（需编辑权限）— 真正打开 .xlsx 提取关键数据"""
    from app.services.prefill_engine import parse_workpaper_real
    result = await parse_workpaper_real(db=db, project_id=project_id, wp_id=wp_id)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# WP Index & Cross-ref endpoints
# ---------------------------------------------------------------------------

@router.get("/wp-index")
async def list_wp_index(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿索引列表（需项目成员权限）"""
    result = await db.execute(
        sa.select(WpIndex)
        .where(WpIndex.project_id == project_id, WpIndex.is_deleted == sa.false())
        .order_by(WpIndex.wp_code)
    )
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "wp_code": i.wp_code,
            "wp_name": i.wp_name,
            "audit_cycle": i.audit_cycle,
            "status": i.status.value if i.status else None,
            "assigned_to": str(i.assigned_to) if i.assigned_to else None,
            "reviewer": str(i.reviewer) if i.reviewer else None,
        }
        for i in items
    ]


@router.get("/wp-cross-refs")
async def list_wp_cross_refs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """交叉索引关系（需项目成员权限）"""
    result = await db.execute(
        sa.select(WpCrossRef)
        .where(WpCrossRef.project_id == project_id)
        .order_by(WpCrossRef.created_at)
    )
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "source_wp_id": str(i.source_wp_id),
            "target_wp_code": i.target_wp_code,
            "cell_reference": i.cell_reference,
        }
        for i in items
    ]


# ═══ 底稿看板视图 + 批量操作 + 编制时间 + 程序联动 ═══

class BatchAssignRequest(BaseModel):
    wp_ids: list[str]
    assigned_to: UUID | None = None
    reviewer: UUID | None = None


class BatchSubmitRequest(BaseModel):
    wp_ids: list[str]


@router.get("/working-papers-kanban")
async def get_workpapers_kanban(
    project_id: UUID,
    audit_cycle: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿看板视图 — 按状态分组统计

    返回4列看板数据：待编制 / 编制中 / 待复核 / 已通过
    每列包含底稿列表（编号/名称/负责人/天数）
    """
    query = sa.select(WpIndex, WorkingPaper).outerjoin(
        WorkingPaper, sa.and_(
            WorkingPaper.wp_index_id == WpIndex.id,
            WorkingPaper.is_deleted == sa.false(),
        )
    ).where(
        WpIndex.project_id == project_id,
        WpIndex.is_deleted == sa.false(),
    )
    if audit_cycle:
        query = query.where(WpIndex.audit_cycle == audit_cycle)
    query = query.order_by(WpIndex.wp_code)

    result = await db.execute(query)
    rows = result.all()

    kanban = {
        "not_started": [],   # 待编制
        "in_progress": [],   # 编制中
        "under_review": [],  # 待复核
        "completed": [],     # 已通过
    }

    for idx_row, wp in rows:
        status = wp.status.value if wp and wp.status else "not_started"
        item = {
            "wp_id": str(wp.id) if wp else None,
            "wp_code": idx_row.wp_code,
            "wp_name": idx_row.wp_name,
            "audit_cycle": idx_row.audit_cycle,
            "status": status,
            "assigned_to": str(wp.assigned_to) if wp and wp.assigned_to else None,
            "reviewer": str(wp.reviewer) if wp and hasattr(wp, 'reviewer') and wp.reviewer else None,
        }

        if status in ("not_started",):
            kanban["not_started"].append(item)
        elif status in ("draft", "edit_complete"):
            kanban["in_progress"].append(item)
        elif status in ("under_review", "review_level1", "review_level2"):
            kanban["under_review"].append(item)
        elif status in ("review_passed", "archived"):
            kanban["completed"].append(item)
        else:
            kanban["in_progress"].append(item)

    # 统计
    stats = {k: len(v) for k, v in kanban.items()}
    stats["total"] = sum(stats.values())
    stats["completion_rate"] = round(stats["completed"] / max(stats["total"], 1) * 100, 1)

    return {"kanban": kanban, "stats": stats}


@router.post("/working-papers/batch-assign")
async def batch_assign(
    project_id: UUID,
    data: BatchAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """批量分配底稿（编制人/复核人）"""
    updated = 0
    for wp_id_str in data.wp_ids:
        wp_id = UUID(wp_id_str)
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
        )
        wp = result.scalar_one_or_none()
        if not wp:
            continue
        if data.assigned_to is not None:
            wp.assigned_to = data.assigned_to
        if data.reviewer is not None:
            wp.reviewer = data.reviewer
        updated += 1

    await db.flush()
    await db.commit()
    return {"updated": updated, "message": f"已批量分配 {updated} 个底稿"}


@router.post("/working-papers/batch-submit")
async def batch_submit_review(
    project_id: UUID,
    data: BatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """批量提交复核（跳过不满足条件的底稿）"""
    submitted = 0
    skipped = []

    for wp_id_str in data.wp_ids:
        wp_id = UUID(wp_id_str)
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
        )
        wp = result.scalar_one_or_none()
        if not wp:
            skipped.append({"wp_id": wp_id_str, "reason": "不存在"})
            continue
        if wp.status != WpFileStatus.edit_complete:
            skipped.append({"wp_id": wp_id_str, "reason": f"状态为{wp.status.value}，需先完成编制"})
            continue

        # 简化门禁：检查复核人是否已分配
        if not wp.reviewer:
            skipped.append({"wp_id": wp_id_str, "reason": "未分配复核人"})
            continue

        wp.status = WpFileStatus.under_review
        submitted += 1

    await db.flush()
    await db.commit()
    return {"submitted": submitted, "skipped": skipped, "message": f"已提交 {submitted} 个，跳过 {len(skipped)} 个"}


@router.post("/working-papers/batch-export")
async def batch_export_zip(
    project_id: UUID,
    data: BatchSubmitRequest,  # 复用 wp_ids 字段
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """批量导出底稿为 ZIP"""
    import io
    import zipfile
    from pathlib import Path

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for wp_id_str in data.wp_ids:
            wp_id = UUID(wp_id_str)
            result = await db.execute(
                sa.select(WorkingPaper, WpIndex)
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
            )
            row = result.first()
            if not row:
                continue
            wp, idx = row
            if wp.file_path:
                fp = Path(wp.file_path)
                if fp.exists():
                    arcname = f"{idx.audit_cycle or 'OTHER'}/{idx.wp_code}.xlsx"
                    zf.write(fp, arcname)

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=workpapers_{project_id}.zip"},
    )


@router.get("/working-papers/{wp_id}/edit-time")
async def get_edit_time(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取底稿编制时间统计

    从审计日志中提取编辑时间段（首次编辑→提交复核）。
    """
    from app.models.core import Log

    # 查找该底稿的编辑相关日志
    result = await db.execute(
        sa.select(Log.created_at, Log.action).where(
            sa.or_(
                sa.and_(Log.action == "workpaper_online_open", Log.new_value.contains(str(wp_id))),
                sa.and_(Log.action == "workpaper_online_save", Log.new_value.contains(str(wp_id))),
            )
        ).order_by(Log.created_at)
    )
    logs = result.all()

    if not logs:
        return {"wp_id": str(wp_id), "total_minutes": 0, "sessions": 0, "message": "无编辑记录"}

    # 计算编辑时间（相邻 open-save 配对）
    total_minutes = 0
    sessions = 0
    first_edit = logs[0][0] if logs else None
    last_edit = logs[-1][0] if logs else None

    # 简化计算：总时长 = 最后一次操作 - 第一次操作
    if first_edit and last_edit and first_edit != last_edit:
        diff = (last_edit - first_edit).total_seconds() / 60
        total_minutes = round(diff, 1)
        sessions = len([l for l in logs if l[1] == "workpaper_online_open"])

    return {
        "wp_id": str(wp_id),
        "total_minutes": total_minutes,
        "sessions": sessions,
        "first_edit": first_edit.isoformat() if first_edit else None,
        "last_edit": last_edit.isoformat() if last_edit else None,
    }


@router.get("/working-papers/{wp_id}/cross-links")
async def get_cross_links(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取底稿间可点击的穿透链接

    返回当前底稿引用的其他底稿列表（含跳转URL）。
    基于 wp_account_mapping.json 的同循环关联 + 交叉索引。
    """
    from app.services.wp_data_rules import get_mapping_for_wp, _load_mapping

    # 获取当前底稿信息
    result = await db.execute(
        sa.select(WpIndex).where(WpIndex.id == (
            sa.select(WorkingPaper.wp_index_id).where(WorkingPaper.id == wp_id).scalar_subquery()
        ))
    )
    idx = result.scalar_one_or_none()
    if not idx:
        return {"links": []}

    wp_code = idx.wp_code
    cycle = idx.audit_cycle

    # 同循环的其他底稿
    mappings = _load_mapping()
    same_cycle = [m for m in mappings if m.get("cycle") == cycle and m.get("wp_code") != wp_code]

    links = []
    for m in same_cycle:
        # 查找该底稿是否存在
        target_result = await db.execute(
            sa.select(WpIndex.id, WorkingPaper.id).outerjoin(
                WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id
            ).where(
                WpIndex.project_id == project_id,
                WpIndex.wp_code == m["wp_code"],
                WpIndex.is_deleted == sa.false(),
            ).limit(1)
        )
        target = target_result.first()
        links.append({
            "wp_code": m["wp_code"],
            "wp_name": m.get("wp_name", ""),
            "exists": target is not None,
            "wp_id": str(target[1]) if target and target[1] else None,
            "jump_url": f"/projects/{project_id}/workpapers?code={m['wp_code']}",
            "relation": "同循环关联",
        })

    # 审定表 ↔ 附注链接
    mapping = get_mapping_for_wp(wp_code)
    if mapping and mapping.get("note_section"):
        links.append({
            "wp_code": f"附注{mapping['note_section']}",
            "wp_name": f"附注 {mapping['note_section']} {mapping.get('account_name', '')}",
            "exists": True,
            "jump_url": f"/projects/{project_id}/disclosure-notes?section={mapping['note_section']}",
            "relation": "对应附注",
        })

    # 审定表 ↔ 报表行次链接
    if mapping and mapping.get("report_row"):
        links.append({
            "wp_code": mapping["report_row"],
            "wp_name": f"报表行次 {mapping['report_row']}",
            "exists": True,
            "jump_url": f"/projects/{project_id}/reports?row={mapping['report_row']}",
            "relation": "对应报表",
        })

    return {"wp_code": wp_code, "links": links, "count": len(links)}


@router.post("/working-papers/{wp_id}/sync-procedure")
async def sync_procedure_status(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """底稿状态与审计程序联动

    底稿提交复核时 → 对应程序实例标记为 completed
    底稿退回时 → 对应程序实例标记为 in_progress
    """
    from app.models.procedure_models import ProcedureInstance

    # 获取底稿编号
    result = await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="底稿不存在")

    wp, idx = row
    wp_code = idx.wp_code
    wp_status = wp.status.value if wp.status else "draft"

    # 映射底稿状态到程序执行状态
    if wp_status in ("under_review", "review_passed", "archived"):
        exec_status = "completed"
    elif wp_status in ("revision_required",):
        exec_status = "in_progress"
    elif wp_status in ("draft", "edit_complete"):
        exec_status = "in_progress"
    else:
        exec_status = "not_started"

    # 更新对应的程序实例
    updated = await db.execute(
        sa.update(ProcedureInstance).where(
            ProcedureInstance.project_id == project_id,
            ProcedureInstance.wp_code == wp_code,
            ProcedureInstance.is_deleted == sa.false(),
        ).values(execution_status=exec_status)
    )

    await db.flush()
    await db.commit()
    return {
        "wp_code": wp_code,
        "wp_status": wp_status,
        "procedure_status": exec_status,
        "updated": updated.rowcount,
    }
