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
    index_status: str | None = Query(None, description="索引层状态过滤（WpIndex.status）"),
    file_status: str | None = Query(None, description="文件/编制层状态过滤（WorkingPaper.status）"),
    assigned_to: UUID | None = None,
    page: int = Query(1, description="页码（正整数）；非法值在底稿查询前返回 422"),
    page_size: int = Query(20, description="每页大小（1..100）；非法值在底稿查询前返回 422"),
    sort: str = Query("wp_code", description="排序字段（已登记：wp_code/audit_cycle/index_status/file_status/created_at/updated_at）"),
    sort_dir: str = Query("asc", description="排序方向 asc/desc"),
    visibility_mode: str | None = Query(None, description="展示模式（仅 UX，不参与授权）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿列表（服务端强制可见性 + 正式分页 / 状态拆分）。

    Feature: procedure-delegation-visibility-isolation · Task 8（组件 C13）。
    - 授权只来自服务端角色分类 + scope + grants（``visibility_mode`` / 客户端身份不改变授权，
      Req 12.1–12.3 / Property 15）。
    - 固定 SQL 顺序：参数校验 → grants → 业务过滤 → 去重 → total/stats → 稳定排序 → 分页。
    - 响应仅 ``{items,total,stats,page,page_size}``（Req 11.6）；拆 ``index_status``/``file_status``。
    - 非法 page/page_size/sort 在底稿查询前返回 HTTP 422（Req 11.7）。
    """
    from app.services.wp_visibility import (
        InvalidListParams,
        VisibilityRoleClassifier,
        WorkpaperListFilters,
        WorkpaperListQueryService,
    )

    context = await VisibilityRoleClassifier(db).classify(current_user, project_id)
    svc = WorkpaperListQueryService(db)
    try:
        return await svc.list_workpapers(
            context,
            page=page,
            page_size=page_size,
            sort=sort,
            sort_dir=sort_dir,
            filters=WorkpaperListFilters(
                audit_cycle=audit_cycle,
                index_status=index_status,
                file_status=file_status,
                assigned_to=assigned_to,
            ),
        )
    except InvalidListParams as exc:
        # 非法分页/排序：在任何底稿数据查询之前返回 422（Req 11.7）
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/my-lead-workpapers")
async def list_my_lead_workpapers(
    project_id: UUID,
    audit_cycle: str | None = None,
    index_status: str | None = Query(None),
    file_status: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    sort: str = Query("wp_code"),
    sort_dir: str = Query("asc"),
    visibility_mode: str | None = Query(None, description="展示模式（仅 UX，不参与授权）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """我的主编底稿（MyLeadWorkpapers，组件 C13 / Req 11.12–11.13）。

    仅返回当前用户作为 Workpaper_Lead（authoritative ``WorkingPaper.assigned_to``）的底稿；
    与"我的程序任务"（assignee/reviewer）为两个独立身份视图，复用同一分页/去重/stats/排序契约。
    响应仅 ``{items,total,stats,page,page_size}``；非法 page/page_size/sort → 422（先于底稿查询）。
    """
    from app.services.wp_visibility import (
        InvalidListParams,
        VisibilityRoleClassifier,
        WorkpaperListFilters,
        WorkpaperListQueryService,
    )

    context = await VisibilityRoleClassifier(db).classify(current_user, project_id)
    svc = WorkpaperListQueryService(db)
    try:
        return await svc.list_lead_workpapers(
            context,
            page=page,
            page_size=page_size,
            sort=sort,
            sort_dir=sort_dir,
            filters=WorkpaperListFilters(
                audit_cycle=audit_cycle,
                index_status=index_status,
                file_status=file_status,
            ),
        )
    except InvalidListParams as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/working-papers/download-pack")
async def download_workpaper_pack(
    project_id: UUID,
    body: DownloadPackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    # Wp_Bound_Gate（Task 4 / R3）：打包底稿正文前用可见集过滤 wp_ids
    # （make_bulk_visible_filter）；不可见/跨项目/未委派/scope 外底稿静默剔除，
    # 不泄露存在性，绝不进入 ZIP（manifest 只由可见集构建）。
    from app.services.wp_visibility.entry_integration import make_bulk_visible_filter

    _visible = make_bulk_visible_filter(
        db, current_user, entrypoint="workpaper.detail", action="read_detail",
        method="GET", entry_family="download",
    )
    visible_wp_ids = [wid for wid in body.wp_ids if await _visible(wid, None)]
    svc = WpDownloadService()
    try:
        buf = await svc.download_pack(
            db=db,
            project_id=project_id,
            wp_ids=visible_wp_ids,
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
    from app.routers._wp_gate import enforce_wp_gate

    # Wp_Bound_Gate：读取底稿详情正文之前完成授权判定（Req 8.1/8.5）。read_detail 只读族；
    # 不可见/跨项目/越权/不存在统一 External_Not_Found（404）。无 project_id 时 gate 从 wp_id 反查。
    await enforce_wp_gate(
        db, current_user,
        entrypoint="workpaper.detail", action="read_detail", method="GET",
        wp_id=wp_id, project_id=project_id, entry_family="detail",
        route_name="/api/projects/{project_id}/working-papers/{wp_id}",
    )

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
    from app.routers._wp_gate import enforce_wp_gate

    # Wp_Bound_Gate：写 parsed_data 前完成授权判定（Req 8.1/8.5）。save_parsed_data 内容写；
    # reviewer/History_Only 被拒（矩阵与 grant 保证）。
    await enforce_wp_gate(
        db, current_user,
        entrypoint="workpaper.parsed_data_write", action="save_parsed_data", method="PUT",
        wp_id=wp_id, project_id=project_id, entry_family="save",
        route_name="/api/projects/{project_id}/working-papers/{wp_id}/parsed-data",
    )

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
    from app.routers._wp_gate import enforce_wp_gate

    # Wp_Bound_Gate：file_status 迁移（写副作用）之前完成授权判定
    # （Req 8.5 / status 入口族 / Part A 已把矩阵状态对齐真实 WpFileStatus）。
    # source_state = 当前 file_status，target_state = 请求状态；仅 lead/admin/supervisor_scope
    # 的完整允许项覆盖真实迁移，assignee/reviewer/History_Only 被拒；越权/不存在统一 404。
    _cur = (
        await db.execute(
            sa.select(WorkingPaper.status).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()
    _src = (_cur.value if hasattr(_cur, "value") else str(_cur)) if _cur is not None else "none"
    await enforce_wp_gate(
        db, current_user,
        entrypoint="workpaper.status_transition", action="status_transition",
        method="POST", wp_id=wp_id, project_id=project_id, entry_family="status",
        route_name="/api/projects/{project_id}/working-papers/{wp_id}/status",
        source_state=_src, target_state=str(data.status),
    )

    svc = WorkingPaperService()
    try:
        result = await svc.update_status(db=db, wp_id=wp_id, new_status=data.status, project_id=project_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
