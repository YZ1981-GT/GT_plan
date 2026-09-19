"""高级查询：底稿回写预览 / 确认端点（独立 router 模块）。

从 ``routers/custom_query.py`` 抽出。回写与只读查询是两个关注点：前者涉及授权顺序、
确认门（旧值复核）与 snapshot 事务写入，后者只读。抽出后 `custom_query.py` 的本次
净增量显著下降（pre-commit 行数门禁要求「优先拆分或抽伴生模块」）。

`WritebackPreviewService`（30KB）此前在 router 层零引用 —— 预览能力已完整实现但
用户从未可达；本模块是其唯一生产入口。

`custom_query` 对本模块的端点与 helper 做 re-export，契约测试对
``router_module.writeback_preview`` 的直调与 monkeypatch 不受影响。

_Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, get_visible_project_ids, require_project_access
from app.models.core import ProjectUser, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/custom-query", tags=["custom-query"])

class WritebackTargetSpec(BaseModel):
    """单个回写目标（preview / confirm 共用）。"""

    new_value: Any = None
    raw: str | None = None
    module: str = "workpaper"
    wp_id: str | None = None
    wp_code: str | None = None
    sheet_name: str | None = None
    cell_ref: str | None = None
    project_id: str | None = None


class WritebackPreviewRequest(BaseModel):
    project_id: str
    targets: list[WritebackTargetSpec] = Field(default_factory=list)


class WritebackConfirmRequest(BaseModel):
    project_id: str
    targets: list[WritebackTargetSpec] = Field(default_factory=list)
    preview_id: str | None = None




def _to_writeback_targets(raw_targets: Any) -> list[Any]:
    """请求体 targets → ``WritebackTarget`` dataclass 列表。"""
    from app.services.custom_query.writeback_preview import WritebackTarget

    built: list[Any] = []
    for item in raw_targets or []:
        data = item if isinstance(item, dict) else item.model_dump()
        built.append(
            WritebackTarget(
                new_value=data.get("new_value"),
                raw=data.get("raw"),
                module=data.get("module") or "workpaper",
                wp_id=data.get("wp_id"),
                wp_code=data.get("wp_code"),
                sheet_name=data.get("sheet_name"),
                cell_ref=data.get("cell_ref"),
            )
        )
    return built


@router.post("/writeback-preview")
async def writeback_preview(
    body: WritebackPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """回写预览：展示每个目标的 ``{addr_id, old_value, new_value}`` 供确认（R9.1）。

    `WritebackPreviewService`（30KB）此前在 router 层零引用 —— 预览能力已完整实现
    但用户从未可达。本端点是其唯一生产入口。
    """
    from app.services.custom_query.writeback_preview import (
        MAX_PREVIEW_ITEMS,
        WritebackPreviewError,
        writeback_preview_service,
    )

    # 从 router 模块取：该 helper 依赖 custom_query 命名空间里可被 monkeypatch
    # 的 get_visible_project_ids，必须在那里定义（见本文件顶部说明）。
    from app.routers.custom_query import _assert_writeback_authorized

    await _assert_writeback_authorized(
        body=body, db=db, current_user=current_user, operation="回写预览"
    )

    if len(body.targets or []) > MAX_PREVIEW_ITEMS:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "PREVIEW_LIMIT_EXCEEDED",
                "message": f"预览目标数超过上限 {MAX_PREVIEW_ITEMS}",
                "actual": len(body.targets or []),
                "limit": MAX_PREVIEW_ITEMS,
            },
        )

    try:
        preview = await writeback_preview_service.generate(
            db, _to_writeback_targets(body.targets), project_id=body.project_id
        )
    except WritebackPreviewError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error_code": exc.error_code, "message": exc.message},
        )
    return preview.to_dict()


@router.post("/writeback-confirm")
async def writeback_confirm(
    body: WritebackConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """回写确认：经确认门校验后逐目标写入（R9.1 / R9.4）。

    确认门（`WritebackConfirmationGate`）复核旧值未被他人改动，避免「预览时看到的
    旧值」与「实际写入时的旧值」不一致造成静默覆盖。
    """
    from app.services.custom_query.writeback_preview import (
        WritebackConfirmationConflict,
        WritebackConfirmationGate,
        WritebackPreviewError,
    )

    # 从 router 模块取：该 helper 依赖 custom_query 命名空间里可被 monkeypatch
    # 的 get_visible_project_ids，必须在那里定义（见本文件顶部说明）。
    from app.routers.custom_query import _assert_writeback_authorized

    await _assert_writeback_authorized(
        body=body, db=db, current_user=current_user, operation="回写确认"
    )

    opened_at_str = request.headers.get("X-File-Opened-At")
    if not opened_at_str:
        raise HTTPException(status_code=400, detail="Missing X-File-Opened-At header")
    try:
        opened_at = datetime.fromisoformat(opened_at_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid X-File-Opened-At format")

    targets = _to_writeback_targets(body.targets)
    gate = WritebackConfirmationGate()
    try:
        await gate.validate(db, targets, project_id=body.project_id)
    except WritebackConfirmationConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"error_code": "WRITEBACK_CONFLICT", "message": str(exc)},
        )
    except WritebackPreviewError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error_code": exc.error_code, "message": exc.message},
        )

    from app.services.custom_query.snapshot_writer import snapshot_writer

    written: list[dict] = []
    for target in targets:
        result = await snapshot_writer.write_cell(
            db=db,
            user=current_user,
            wp_id=target.wp_id or target.wp_code,
            sheet_name=target.sheet_name,
            cell_ref=target.cell_ref,
            new_value=target.new_value,
            opened_at=opened_at,
            module=target.module,
            project_id=body.project_id,
        )
        written.append(result if isinstance(result, dict) else {"result": "ok"})
    await db.commit()

    # Task 16 / Requirement 13.1 / Property 52：snapshot_writer 在事务内只把
    # WORKPAPER_SAVED 写成耐久 outbox 行，事件必须在 content commit 之后才发布。
    from app.services.workpaper_sync.outbox import DurableEventOutboxService

    await DurableEventOutboxService.publish_pending(db)

    return {"success": True, "written": written, "count": len(written)}
