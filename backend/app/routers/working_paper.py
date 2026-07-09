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

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.core.field_selection import parse_fields, DEFAULT_SUMMARY_FIELDS, BLOCKED_FIELDS
from app.deps import require_project_access, check_consol_lock
from app.models.core import User
from app.models.phase10_schemas import DownloadPackRequest
from app.services.working_paper_service import WorkingPaperService
from app.services.project_audit_year import fetch_project_audit_year
from app.services.wp_download_service import WpDownloadService, WpUploadService
from app.models.workpaper_models import WpIndex, WpCrossRef, WorkingPaper, WpFileStatus

# 共享请求模型已抽到 schemas/workpaper_requests.py（供子 router 复用，避免反向依赖）。
# 此处 re-export 保持 `from app.routers.working_paper import UploadRequest` 等向后兼容。
from app.schemas.workpaper_requests import (
    UploadRequest,
    StatusUpdateRequest,
    AssignRequest,
    ReviewStatusRequest,
)

# 在线编辑域端点已拆到 wp_editor_router.py（含 _prefill_word_template /
# _push_representation_letter_date helper）。此处 re-export 保持
# `from app.routers.working_paper import _push_representation_letter_date` 等向后兼容
# （test_a16_cw76_sign_date.py 依赖）。
from app.routers.wp_editor_router import (  # noqa: F401
    _prefill_word_template,
    _push_representation_letter_date,
    save_univer_data,
)

# 复核+分配域端点已拆到 wp_review_router.py（含 _send_reassignment_notifications helper，
# 随唯一调用方 assign_workpaper 同模块）。此处 re-export 保持
# `from app.routers.working_paper import _send_reassignment_notifications` 等向后兼容
# （test_reassignment_notifications.py 依赖）。
from app.routers.wp_review_router import (  # noqa: F401
    _send_reassignment_notifications,
    assign_workpaper,
    submit_review,
    update_review_status,
)

# 批量+看板域端点已拆到 wp_batch_router.py（含 BatchAssignRequest / BatchSubmitRequest 模型）。
# 此处 re-export 保持 `from app.routers.working_paper import batch_assign` 等向后兼容。
from app.routers.wp_batch_router import (  # noqa: F401
    BatchAssignRequest,
    BatchSubmitRequest,
    get_workpapers_kanban,
    batch_assign,
    batch_submit_review,
    batch_export_zip,
    get_edit_time,
)

# 关系/索引域端点已拆到 wp_relation_router.py。此处 re-export 保持
# `from app.routers.working_paper import list_wp_index` 等向后兼容。
from app.routers.wp_relation_router import (  # noqa: F401
    list_wp_index,
    list_wp_cross_refs,
    get_cross_links,
    get_wp_relation_graph,
    sync_procedure_status,
)

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["working-papers"],
)


# ---------------------------------------------------------------------------
# Working paper endpoints
# ---------------------------------------------------------------------------

@router.get("/working-papers")
async def list_workpapers(
    project_id: UUID,
    audit_cycle: str | None = None,
    status: str | None = None,
    assigned_to: UUID | None = None,
    fields: str | None = Query(None, description="逗号分隔的字段名，如 id,wp_code,status"),
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
    items = await svc.list_workpapers(
        db=db,
        project_id=project_id,
        audit_cycle=audit_cycle,
        status=status,
        assigned_to=assigned_to,
        scope_cycles=scope_cycles,
    )

    # 字段选择：过滤返回字段
    requested_fields = parse_fields(fields)
    if requested_fields is not None:
        # 移除屏蔽字段
        allowed = requested_fields - BLOCKED_FIELDS
        # 确保至少包含 id
        allowed.add("id")
        items = [
            {k: v for k, v in item.items() if k in allowed}
            for item in items
        ]
    else:
        # 默认行为：使用默认摘要字段集排除大字段
        # 保持向后兼容 — 现有返回字段不含 parsed_data，无需额外过滤
        pass

    return items


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
        from urllib.parse import quote

        file_path = Path(info["file_path"])
        file_name = info["file_name"]
        # RFC 5987: 中文文件名用 filename* 编码，ASCII 回退用 filename
        ascii_name = file_name.encode("ascii", "ignore").decode() or "workpaper.xlsx"
        utf8_name = quote(file_name, safe="")
        disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"

        return StreamingResponse(
            open(file_path, "rb"),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": disposition,
                "X-WP-Version": str(info["file_version"]),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── A16 声明书专用端点（file-info / sign-status / onlyoffice-config） ──────


@router.get("/working-papers/{wp_id}/file-info")
async def get_workpaper_file_info(
    project_id: UUID,
    wp_id: UUID,
    version: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
):
    """返回底稿文件信息 + 签发状态（A16 声明书用；optional version 按子码隔离）"""
    wp = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # 签发状态从 field_overrides 读取（scope=word_template:A16, field=value）
    from app.services.field_override_service import FieldOverrideService
    from app.models.workpaper_models import WpIndex

    wp_index = (await db.execute(
        sa.select(WpIndex.wp_code).where(WpIndex.id == wp.wp_index_id)
    )).scalar_one_or_none()
    wp_code = wp_index or ""

    svc = FieldOverrideService(db)
    year_val = await fetch_project_audit_year(db, project_id) or 0

    sign_status = None
    if year_val:
        if version and wp_code == "A16":
            scope = f"word_template:A16:{version}"
        else:
            scope = f"word_template:{wp_code}"
        sign_status = await svc.get(project_id, year_val, scope, "sign_status", "value")

    return {
        "file_name": wp.file_path.split("/")[-1] if wp.file_path else f"{version or wp_code} 声明书.docx",
        "file_path": wp.file_path,
        "file_version": wp.file_version,
        "sign_status": sign_status or "pending",
        "version": version,
    }












@router.post("/working-papers/{wp_id}/upload")
async def upload_workpaper(
    project_id: UUID,
    wp_id: UUID,
    data: UploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
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
    _lock_check=Depends(check_consol_lock),
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


@router.put("/working-papers/{wp_id}/parsed-data")
async def update_parsed_data(
    project_id: UUID,
    wp_id: UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """更新底稿 parsed_data（结构化组件数据持久化）。

    合并语义：payload 会 shallow merge 到现有 parsed_data 上，
    不覆盖 univer_snapshot 等其他键。
    """
    from sqlalchemy.orm.attributes import flag_modified

    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == False)
    )).scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    existing = dict(wp.parsed_data) if isinstance(wp.parsed_data, dict) else {}
    existing.update(payload)
    wp.parsed_data = existing
    flag_modified(wp, "parsed_data")
    await db.flush()
    await db.commit()
    return {"ok": True}


@router.put("/working-papers/{wp_id}/status")
async def update_status(
    project_id: UUID,
    wp_id: UUID,
    data: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
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
