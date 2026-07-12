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
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.base import ProjectStatus
from app.models.core import Project, ProjectUser, User
from app.services.bulk_tab.bulk_progress import bulk_progress_service

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


class RollbackRequest(BaseModel):
    """回滚请求体。"""

    import_id: str = Field(..., description="导入操作 ID")
    snapshots: list[dict[str, str]] = Field(
        ..., description="快照记录列表 [{wp_id, snapshot_id}]"
    )


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
# POST /import — 批量导入（multipart ZIP）
# ---------------------------------------------------------------------------


@router.post("/import")
async def bulk_import(
    project_id: UUID,
    file: UploadFile = File(..., description="ZIP 文件（bulk-tab 数据包）"),
    dryRun: bool = Query(default=False, description="预检模式：True=不写库"),
    strategy: str = Query(
        default="overwrite", description="冲突策略: overwrite/fill-empty/reject"
    ),
    current_user: User = Depends(require_project_access("edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """批量导入底稿 Tab 数据（multipart ZIP）。

    - dryRun=True → 仅校验（manifest/完整性/状态门禁），不写库（Req 2.3）
    - dryRun=False → 正式导入（含快照 → 逐 sheet 写入 → 审计日志）
    - strategy: overwrite（默认）/ fill-empty / reject

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

    if dryRun:
        report = await bulk_import_service.dry_run(
            db=db,
            project_id=project_id_str,
            zip_bytes=zip_bytes,
            strategy=strategy,
        )
    else:
        report = await bulk_import_service.run(
            db=db,
            project_id=project_id_str,
            zip_bytes=zip_bytes,
            strategy=strategy,
            user=current_user,
        )
        # 正式导入成功后 commit（service 只 flush 不 commit）
        await db.commit()

    return report.to_dict()


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
