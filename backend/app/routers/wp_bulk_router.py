"""批量导入导出路由 — workpaper-bulk-tab-import-export

端点清单：
- POST /api/projects/{project_id}/bulk-tab/export-templates  → ZIP（≥只读）
- POST /api/projects/{project_id}/bulk-tab/export-data        → ZIP（≥只读）
- POST /api/projects/{project_id}/bulk-tab/import             → ImportReport（编制权）
- POST /api/projects/{project_id}/bulk-tab/import/rollback    → 回滚（项目经理）
- GET  /api/projects/{project_id}/bulk-tab/progress/{task_id} → SSE 进度（≥只读）

注册到 router_registry/workpaper.py §120。

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 6.1
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any
from urllib.parse import quote
from uuid import UUID

# ─── Single-flight: prevent duplicate concurrent exports for same project (#33) ───
_PROJECT_EXPORT_LOCKS: dict[str, asyncio.Lock] = {}

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.base import ProjectStatus
from app.models.core import Project, ProjectUser, User
from app.services.bulk_tab.bulk_progress import bulk_progress_service
from app.services.wp_visibility.entry_integration import (
    make_bulk_preflight,
    make_bulk_visible_filter,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/bulk-tab",
    tags=["bulk-tab"],
)


# ---------------------------------------------------------------------------
# GET /progress/{task_id} — SSE 进度流
# ---------------------------------------------------------------------------


@router.get("/progress/{task_id}")
async def get_bulk_progress_stream(
    project_id: UUID,
    task_id: str,
    current_user: User = Depends(require_project_access("readonly")),
):
    """SSE 进度流 — 实时推送批量导入/导出进度。

    事件格式：
      event: progress
      data: {"type": "progress", "current": N, "total": M, "message": "..."}

      event: complete
      data: {"type": "complete", "current": N, "total": M, "message": "完成"}

      event: error
      data: {"type": "error", "current": N, "total": M, "message": "错误信息"}

    终态事件（complete/error）发送后流自动关闭。
    无活动时每 30 秒发送 keepalive 注释行。

    Requirements: 6.1
    """
    # 验证任务存在
    task = bulk_progress_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    # 验证任务属于当前项目
    if task.project_id != str(project_id):
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    # 如果任务已完成/失败，直接返回终态
    if task.status in ("complete", "failed"):
        async def terminal_generator():
            if task.status == "complete":
                event_data = {
                    "type": "complete",
                    "current": task.current,
                    "total": task.total,
                    "message": task.message or "完成",
                }
                yield f"event: complete\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"
            else:
                event_data = {
                    "type": "error",
                    "current": task.current,
                    "total": task.total,
                    "message": task.error or "未知错误",
                }
                yield f"event: error\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            terminal_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # 订阅实时进度
    queue = bulk_progress_service.subscribe(task_id)

    async def event_generator():
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = message.get("type", "progress")
                    data = json.dumps(message, ensure_ascii=False, default=str)
                    yield f"event: {event_type}\ndata: {data}\n\n"

                    # 终态事件 — 关闭流
                    if event_type in ("complete", "error"):
                        break
                except asyncio.TimeoutError:
                    # 发送 keepalive 保持连接
                    yield ": keepalive\n\n"
        finally:
            bulk_progress_service.unsubscribe(task_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class ExportTemplatesRequest(BaseModel):
    """导出模板请求体。"""

    cycles: list[str] | None = Field(
        default=None, description="审计循环多选（如 ['D','K']）；None/空 = 全部含 I/E 的循环"
    )
    password: str | None = Field(
        default=None, description="ZIP 密码保护（可选，留空则不加密）"
    )


class ExportDataRequest(BaseModel):
    """导出数据请求体。"""

    cycles: list[str] | None = Field(
        default=None, description="审计循环多选；None/空 = 全部含 I/E 的循环"
    )
    only_with_data: bool = Field(
        default=False, description="仅导出有数据的 Tab（跳过空表），Req 3.3"
    )
    incremental: bool = Field(
        default=False, description="增量导出：跳过自上次导出后未变更的 Tab（sha256 比对）"
    )
    password: str | None = Field(
        default=None, description="ZIP 密码保护（可选，留空则不加密）"
    )


class AsyncTaskResponse(BaseModel):
    """异步任务受理响应。"""

    task_id: str = Field(..., description="任务 ID，用于 SSE 进度订阅与结果查询")
    status: str = Field(default="accepted", description="受理状态")


class RollbackRequest(BaseModel):
    """回滚请求体。"""

    import_id: str = Field(..., description="导入操作 ID")
    snapshots: list[dict[str, str]] = Field(
        ..., description="快照记录列表 [{wp_id, snapshot_id}]"
    )


# ---------------------------------------------------------------------------
# Helpers — 导出
# ---------------------------------------------------------------------------


def _bulk_zip_disposition(filename: str) -> str:
    """构造 RFC5987 编码的 Content-Disposition 头值（支持中文文件名）。

    平台铁律：StreamingResponse 中文文件名必须 RFC5987 编码。
    """
    encoded = quote(filename, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


async def _load_project_meta(db: AsyncSession, project_id: UUID) -> tuple[Project, int]:
    """加载项目并返回 (project, audit_year)。项目不存在抛 404。"""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    audit_year = project.audit_year or 0
    return project, audit_year


def _build_zip_filename(project: Project, audit_year: int, mode_label: str) -> str:
    """生成 ZIP 文件名: {项目名}_{年度}_底稿批量{模板|数据}.zip。"""
    parts: list[str] = []
    base = project.short_name or project.name or "项目"
    parts.append(base)
    if audit_year:
        parts.append(str(audit_year))
    parts.append(f"底稿批量{mode_label}")
    return "_".join(parts) + ".zip"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _check_project_importable(
    db: AsyncSession, project_id: UUID
) -> None:
    """检查项目是否允许导入（只读/锁定/归档拒绝）。

    Req 5.5: IF 项目为只读或已锁定，THEN 拒绝导入请求。
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 归档项目拒绝导入
    if project.status == ProjectStatus.archived:
        raise HTTPException(
            status_code=423,
            detail={
                "error_code": "PROJECT_ARCHIVED",
                "message": "项目已归档，无法导入",
            },
        )

    # 合并锁定拒绝导入
    if project.consol_lock:
        raise HTTPException(
            status_code=423,
            detail={
                "error_code": "PROJECT_LOCKED",
                "message": "项目已被合并锁定，无法导入",
            },
        )


async def _require_manager_role(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """要求项目经理或更高权限角色（manager / partner / admin）。

    Req 5.4: 回滚要求项目经理或同等角色权限。
    """
    role = current_user.role.value

    # admin / partner 全局放行
    if role in ("admin", "partner"):
        return current_user

    # 查询项目角色
    from sqlalchemy import select

    result = await db.execute(
        select(ProjectUser.role).where(
            ProjectUser.project_id == project_id,
            ProjectUser.user_id == current_user.id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    )
    project_role = result.scalar_one_or_none()

    if project_role is None:
        raise HTTPException(status_code=403, detail="权限不足：需要项目经理角色")

    project_role_value = (
        project_role.value if hasattr(project_role, "value") else str(project_role)
    )

    # manager / partner 允许回滚
    if project_role_value not in ("manager", "partner"):
        raise HTTPException(status_code=403, detail="权限不足：需要项目经理角色")

    return current_user


# ---------------------------------------------------------------------------
# POST /preview-manifest — 从上传 ZIP 预览 manifest（#16 自动识别循环）
# ---------------------------------------------------------------------------


@router.post("/preview-manifest")
async def preview_manifest(
    project_id: UUID,
    file: UploadFile = File(...),
    _user: User = Depends(get_current_user),
):
    """Preview manifest.json from uploaded ZIP without importing."""
    import zipfile

    # Limit: only read first 100MB to prevent OOM
    MAX_PREVIEW_SIZE = 100 * 1024 * 1024  # 100MB
    content = await file.read(MAX_PREVIEW_SIZE + 1)
    if len(content) > MAX_PREVIEW_SIZE:
        return {"cycles": [], "file_count": 0, "mode": "", "exported_at": "", "warning": "文件过大，请手动选择循环"}

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            if 'manifest.json' in zf.namelist():
                manifest_data = json.loads(zf.read('manifest.json'))
                return {
                    "cycles": manifest_data.get("cycles", []),
                    "file_count": len(manifest_data.get("files", [])),
                    "mode": manifest_data.get("mode", ""),
                    "exported_at": manifest_data.get("exported_at", ""),
                }
    except Exception:
        pass
    return {"cycles": [], "file_count": 0, "mode": "", "exported_at": ""}


# ---------------------------------------------------------------------------
# POST /export-templates — 批量导出模板 ZIP
# ---------------------------------------------------------------------------


@router.post("/export-templates")
async def bulk_export_templates(
    project_id: UUID,
    body: ExportTemplatesRequest,
    current_user: User = Depends(require_project_access("readonly")),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """批量导出底稿 Tab **模板**为 ZIP（空表结构 + 编制提示）。

    - 循环多选（body.cycles）；None/空 = 全部含 I/E 的循环
    - 权限：≥ 只读（require_project_access("readonly")），Req 5.1
    - 返回 application/zip，中文文件名 RFC5987 编码

    Requirements: 1.1, 3.1, 5.1
    """
    from app.core.build_version import get_build_version
    from app.services.bulk_tab import bulk_export_service

    project, audit_year = await _load_project_meta(db, project_id)

    try:
        platform_version = get_build_version().get("git_commit", "")
    except Exception:
        platform_version = ""

    # ─── Single-flight per-project lock (#33) ─────────────────────────
    _lock_key = str(project_id)
    if _lock_key not in _PROJECT_EXPORT_LOCKS:
        _PROJECT_EXPORT_LOCKS[_lock_key] = asyncio.Lock()
    if _PROJECT_EXPORT_LOCKS[_lock_key].locked():
        logger.info("bulk_export_templates: concurrent export already running for project %s, queuing", project_id)

    async with _PROJECT_EXPORT_LOCKS[_lock_key]:
        zip_buffer = await bulk_export_service.export(
            db=db,
            project_id=project_id,
            cycles=body.cycles or None,
            mode="template",
            password=body.password or None,
            exported_by=current_user.username,
            platform_version=platform_version,
            audit_year=audit_year,
            # Task 10 · manifest 只由可见集构建（Req 8.6/9）
            visible_filter=make_bulk_visible_filter(db, current_user),
        )

    zip_buffer.seek(0)

    filename = _build_zip_filename(project, audit_year, "模板")
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": _bulk_zip_disposition(filename)},
    )


# ---------------------------------------------------------------------------
# POST /export-data — 批量导出数据 ZIP
# ---------------------------------------------------------------------------


@router.post("/export-data")
async def bulk_export_data(
    project_id: UUID,
    body: ExportDataRequest,
    current_user: User = Depends(require_project_access("readonly")),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """批量导出底稿 Tab **数据**为 ZIP（含已填写数据快照）。

    - 循环多选（body.cycles）；None/空 = 全部含 I/E 的循环
    - only_with_data=True → 仅导出有数据的 Tab（跳过空表），Req 3.3
    - 权限：≥ 只读（require_project_access("readonly")），Req 5.2
    - 返回 application/zip，中文文件名 RFC5987 编码

    Requirements: 1.2, 3.1, 3.3, 5.2
    """
    from app.core.build_version import get_build_version
    from app.services.bulk_tab import bulk_export_service

    project, audit_year = await _load_project_meta(db, project_id)

    try:
        platform_version = get_build_version().get("git_commit", "")
    except Exception:
        platform_version = ""

    # ─── Single-flight per-project lock (#33) ─────────────────────────
    _lock_key = str(project_id)
    if _lock_key not in _PROJECT_EXPORT_LOCKS:
        _PROJECT_EXPORT_LOCKS[_lock_key] = asyncio.Lock()
    if _PROJECT_EXPORT_LOCKS[_lock_key].locked():
        logger.info("bulk_export_data: concurrent export already running for project %s, queuing", project_id)

    async with _PROJECT_EXPORT_LOCKS[_lock_key]:
        zip_buffer = await bulk_export_service.export(
            db=db,
            project_id=project_id,
            cycles=body.cycles or None,
            mode="data",
            only_with_data=body.only_with_data,
            incremental=body.incremental,
            password=body.password or None,
            exported_by=current_user.username,
            platform_version=platform_version,
            audit_year=audit_year,
            # Task 10 · manifest 只由可见集构建（Req 8.6/9）
            visible_filter=make_bulk_visible_filter(db, current_user),
        )

    zip_buffer.seek(0)

    filename = _build_zip_filename(project, audit_year, "数据")
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": _bulk_zip_disposition(filename)},
    )


# ---------------------------------------------------------------------------
# POST /export-templates/async · /export-data/async — 大项目异步导出（Req 6.1）
# ---------------------------------------------------------------------------


async def _platform_version() -> str:
    from app.core.build_version import get_build_version

    try:
        return get_build_version().get("git_commit", "")
    except Exception:
        return ""


@router.post("/export-templates/async", response_model=AsyncTaskResponse)
async def bulk_export_templates_async(
    project_id: UUID,
    body: ExportTemplatesRequest,
    current_user: User = Depends(require_project_access("readonly")),
    db: AsyncSession = Depends(get_db),
) -> AsyncTaskResponse:
    """大项目异步导出**模板** ZIP：立即返回 task_id，后台生成，SSE 推进度。

    进度订阅：`GET /progress/{task_id}`；完成后 `GET /export/{task_id}/download`。

    Requirements: 6.1
    """
    from app.services.bulk_tab import bulk_async_runner

    project, audit_year = await _load_project_meta(db, project_id)
    filename = _build_zip_filename(project, audit_year, "模板")

    task_id = bulk_async_runner.schedule_export(
        project_id=project_id,
        cycles=body.cycles or None,
        mode="template",
        only_with_data=False,
        exported_by=current_user.username,
        platform_version=await _platform_version(),
        audit_year=audit_year,
        user_id=str(current_user.id),
        filename=filename,
        password=body.password or None,
    )
    return AsyncTaskResponse(task_id=task_id)


@router.post("/export-data/async", response_model=AsyncTaskResponse)
async def bulk_export_data_async(
    project_id: UUID,
    body: ExportDataRequest,
    current_user: User = Depends(require_project_access("readonly")),
    db: AsyncSession = Depends(get_db),
) -> AsyncTaskResponse:
    """大项目异步导出**数据** ZIP：立即返回 task_id，后台生成，SSE 推进度。

    Requirements: 6.1
    """
    from app.services.bulk_tab import bulk_async_runner

    project, audit_year = await _load_project_meta(db, project_id)
    filename = _build_zip_filename(project, audit_year, "数据")

    task_id = bulk_async_runner.schedule_export(
        project_id=project_id,
        cycles=body.cycles or None,
        mode="data",
        only_with_data=body.only_with_data,
        exported_by=current_user.username,
        platform_version=await _platform_version(),
        audit_year=audit_year,
        user_id=str(current_user.id),
        filename=filename,
        password=body.password or None,
        incremental=body.incremental,
    )
    return AsyncTaskResponse(task_id=task_id)


# ---------------------------------------------------------------------------
# GET /export/{task_id}/download — 下载异步导出的 ZIP 结果
# ---------------------------------------------------------------------------


@router.get("/export/{task_id}/download")
async def bulk_export_download(
    project_id: UUID,
    task_id: str,
    current_user: User = Depends(require_project_access("readonly")),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """下载已完成的异步导出 ZIP（Req 6.1）。

    Wp_Bound_Gate（Task 4 / R3）：manifest 已在生成阶段（bulk_async_runner）仅由可见集构建；
    下载端 ① 校验 task 归属发起人（仅发起人可下载其导出）；② 对生成时记录的可见底稿集合在
    下载时 re-gate（Req 8.16）——排队/生成后被撤权、任一 wp 变不可见 → 统一 404，不泄露存在性。
    """
    from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL

    task = bulk_progress_service.get_task(task_id)
    if not task or task.project_id != str(project_id):
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    # ① 归属发起人（防止下载他人导出）→ 统一 404
    if task.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail=EXTERNAL_NOT_FOUND_DETAIL)
    # ② 下载时 re-gate 生成阶段记录的可见 wp 集合（撤权即拒绝）
    _visible = make_bulk_visible_filter(
        db, current_user, entrypoint="workpaper.detail", action="read_detail",
        method="GET", entry_family="bulk",
    )
    for _wid in (task.wp_ids or []):
        if not await _visible(_wid, None):
            raise HTTPException(status_code=404, detail=EXTERNAL_NOT_FOUND_DETAIL)
    if task.status != "complete" or not task.result_path:
        raise HTTPException(status_code=409, detail="导出尚未完成")

    import os

    if not os.path.exists(task.result_path):
        raise HTTPException(status_code=410, detail="导出文件已被清理")

    filename = task.result_filename or "bulk_export.zip"
    return FileResponse(
        task.result_path,
        media_type="application/zip",
        headers={"Content-Disposition": _bulk_zip_disposition(filename)},
    )


# ---------------------------------------------------------------------------
# POST /import — 批量导入（multipart ZIP）
# ---------------------------------------------------------------------------


@router.post("/import")
async def bulk_import(
    project_id: UUID,
    file: UploadFile = File(..., description="ZIP 文件（bulk-tab 数据包）"),
    dry_run: bool = Form(default=False, description="预检模式：True=不写库"),
    strategy: str = Form(
        default="overwrite", description="冲突策略: overwrite/fill-empty/reject"
    ),
    cycles: str | None = Form(
        default=None, description="循环多选 JSON 串（仅记录，导入范围以 ZIP manifest 为准）"
    ),
    current_user: User = Depends(require_project_access("edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """批量导入底稿 Tab 数据（multipart ZIP）。

    - dry_run=True → 仅校验（manifest/完整性/状态门禁），不写库（Req 2.3）
    - dry_run=False → 正式导入（含快照 → 逐 sheet 写入 → 审计日志）
    - strategy: overwrite（默认）/ fill-empty / reject

    表单字段（对齐前端 useBulkTabImportExport.ts）：file / dry_run / strategy / cycles。

    权限：编制权（require_project_access("edit")），Req 5.3
    门禁：只读/锁定项目拒绝，Req 5.5

    Requirements: 2.3, 5.3, 5.5
    """
    # Req 5.5: 检查项目可导入性（归档/锁定拒绝）
    await _check_project_importable(db, project_id)

    # 校验策略值
    valid_strategies = ("overwrite", "fill-empty", "reject")
    if strategy not in valid_strategies:
        raise HTTPException(
            status_code=400,
            detail=f"无效的冲突策略: '{strategy}'。可选值: {', '.join(valid_strategies)}",
        )

    # 读取上传的 ZIP 文件
    try:
        zip_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件读取失败: {e}")

    if not zip_bytes:
        raise HTTPException(status_code=400, detail="上传文件为空")

    # 调用 service 层
    from app.services.bulk_tab import bulk_import_service

    project_id_str = str(project_id)

    # Task 10 · 逐资源 gate preflight（Req 8.13/8.14/9）：写入前对每个目标底稿过 gate，
    # 显式任一被拒 → 整请求 404（原子，副作用前）。
    preflight = make_bulk_preflight(db, current_user)

    if dry_run:
        report = await bulk_import_service.dry_run(
            db=db,
            project_id=project_id_str,
            zip_bytes=zip_bytes,
            strategy=strategy,
            preflight=preflight,
        )
    else:
        report = await bulk_import_service.run(
            db=db,
            project_id=project_id_str,
            zip_bytes=zip_bytes,
            strategy=strategy,
            user=current_user,
            preflight=preflight,
        )
        # 正式导入成功后 commit（service 只 flush 不 commit）
        await db.commit()

    return report.to_dict()


# ---------------------------------------------------------------------------
# POST /import/async — 大项目异步导入（Req 6.1, 4.2）
# ---------------------------------------------------------------------------


@router.post("/import/async", response_model=AsyncTaskResponse)
async def bulk_import_async(
    project_id: UUID,
    file: UploadFile = File(..., description="ZIP 文件（bulk-tab 数据包）"),
    strategy: str = Form(
        default="overwrite", description="冲突策略: overwrite/fill-empty/reject"
    ),
    all_or_nothing: bool = Form(
        default=False, description="all-or-nothing 原子性：任一 sheet 失败则全量回滚（Req 4.2）"
    ),
    current_user: User = Depends(require_project_access("edit")),
    db: AsyncSession = Depends(get_db),
) -> AsyncTaskResponse:
    """大项目异步导入：立即返回 task_id，后台跑导入，SSE 推进度（Req 6.1）。

    - `all_or_nothing=True` → AtomicityMode.ALL_OR_NOTHING（任一失败全回滚，Req 4.2）
    - 完成后 `GET /import/{task_id}/result` 查 ImportReport；进度 `GET /progress/{task_id}`
    - 门禁：编制权 + 只读/锁定项目拒绝（Req 5.3, 5.5）

    Requirements: 6.1, 6.2, 4.2
    """
    from app.services.bulk_tab import bulk_async_runner
    from app.services.bulk_tab.snapshot_guard import AtomicityMode

    # Req 5.5: 项目可导入性门禁（归档/锁定拒绝）
    await _check_project_importable(db, project_id)

    valid_strategies = ("overwrite", "fill-empty", "reject")
    if strategy not in valid_strategies:
        raise HTTPException(
            status_code=400,
            detail=f"无效的冲突策略: '{strategy}'。可选值: {', '.join(valid_strategies)}",
        )

    try:
        zip_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件读取失败: {e}")
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="上传文件为空")

    atomicity = (
        AtomicityMode.ALL_OR_NOTHING if all_or_nothing else AtomicityMode.PER_SHEET
    )
    task_id = bulk_async_runner.schedule_import(
        project_id=project_id,
        zip_bytes=zip_bytes,
        strategy=strategy,
        atomicity=atomicity,
        user_id=current_user.id,
        username=current_user.username,
        role_value=current_user.role.value,
    )
    return AsyncTaskResponse(task_id=task_id)


# ---------------------------------------------------------------------------
# GET /import/{task_id}/result — 查询异步导入结果报告
# ---------------------------------------------------------------------------


@router.get("/import/{task_id}/result")
async def bulk_import_result(
    project_id: UUID,
    task_id: str,
    current_user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """查询已完成的异步导入 ImportReport（Req 6.1）。"""
    task = bulk_progress_service.get_task(task_id)
    if not task or task.project_id != str(project_id):
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    if task.status == "failed":
        return {"status": "failed", "error": task.error}
    if task.status != "complete" or task.result is None:
        raise HTTPException(status_code=409, detail="导入尚未完成")
    return {"status": "complete", "report": task.result}


# ---------------------------------------------------------------------------
# POST /import/rollback — 回滚导入
# ---------------------------------------------------------------------------


@router.post("/import/rollback")
async def bulk_import_rollback(
    project_id: UUID,
    body: RollbackRequest,
    current_user: User = Depends(_require_manager_role),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """按 import_id 回滚批量导入（恢复到快照状态）。

    权限：项目经理或同等角色（Req 5.4）。

    Requirements: 5.4, 6.2
    """
    from app.services.bulk_tab.snapshot_guard import SnapshotGuard, SnapshotRecord

    # 构造 SnapshotRecord 列表
    snapshots: list[SnapshotRecord] = []
    for snap in body.snapshots:
        wp_id = snap.get("wp_id")
        snapshot_id = snap.get("snapshot_id")
        if not wp_id or not snapshot_id:
            continue
        try:
            snapshots.append(
                SnapshotRecord(
                    wp_id=UUID(wp_id),
                    snapshot_id=UUID(snapshot_id),
                )
            )
        except (ValueError, TypeError):
            continue

    if not snapshots:
        raise HTTPException(status_code=400, detail="无有效的快照记录")

    # Wp_Bound_Gate（Task 4 / R3）：按快照还原底稿正文前逐资源 preflight（make_bulk_preflight）；
    # 任一目标底稿不可见/跨项目/未委派 → 抛 ExternalNotFound(404)，整请求原子失败于回滚副作用前
    # （仅回滚可见+可写底稿；排队期间被撤权即拒绝，不 fail-soft 跳过）。
    preflight = make_bulk_preflight(
        db, current_user, entrypoint="workpaper.import", action="import_data",
        method="POST", entry_family="bulk",
    )
    for _snap in snapshots:
        await preflight(_snap.wp_id, None)

    # 执行回滚
    user_id = current_user.id
    await SnapshotGuard.rollback(
        db,
        snapshots,
        project_id=project_id,
        user_id=user_id,
    )

    await db.commit()

    return {
        "success": True,
        "import_id": body.import_id,
        "rolled_back_count": len(snapshots),
    }
