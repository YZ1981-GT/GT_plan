"""底稿版本链 API 路由

- POST /api/projects/{pid}/workpapers/{wp_id}/versions — 创建快照
- GET  /api/projects/{pid}/workpapers/{wp_id}/versions — 分页列表
- GET  /api/projects/{pid}/workpapers/{wp_id}/versions/{vid} — 快照详情
- POST /api/projects/{pid}/workpapers/{wp_id}/versions/compare — diff 对比
- POST /api/projects/{pid}/workpapers/{wp_id}/versions/{vid}/rollback — 回滚

注册: router_registry/collaboration.py §130 (Task 17)
Tables: workpaper_snapshots (V096)

Validates: Requirements 5.6, 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.version_trail_service import (
    CompareRequest,
    DiffResult,
    SnapshotCreate,
    SnapshotDetail,
    SnapshotMeta,
    VersionTrailService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{pid}/workpapers/{wp_id}/versions",
    tags=["version-trail"],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


# 回滚允许的角色（现场经理+）
_ROLLBACK_ALLOWED_ROLES = {"admin", "partner", "manager", "qc"}


async def _validate_workpaper_belongs_to_project(
    db: AsyncSession, pid: UUID, wp_id: UUID
) -> None:
    """验证底稿属于指定项目（安全隔离）。"""
    row = (
        await db.execute(
            text(
                "SELECT 1 FROM working_paper "
                "WHERE id = :wp_id AND project_id = :pid AND is_deleted = false "
                "LIMIT 1"
            ),
            {"wp_id": wp_id, "pid": pid},
        )
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="底稿不存在或不属于该项目")


# ─── POST /versions — 创建快照 ───────────────────────────────────────────────


@router.post("", response_model=SnapshotMeta)
async def create_version(
    pid: UUID,
    wp_id: UUID,
    body: SnapshotCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SnapshotMeta:
    """创建版本快照。"""
    await _validate_workpaper_belongs_to_project(db, pid, wp_id)

    result = await VersionTrailService.create_snapshot(
        db=db,
        project_id=pid,
        workpaper_id=wp_id,
        user_id=current_user.id,
        snapshot_type=body.snapshot_type,
        description=body.description,
        change_summary=body.change_summary,
    )
    await db.commit()
    return result


# ─── GET /versions — 分页列表 ────────────────────────────────────────────────


@router.get("")
async def list_versions(
    pid: UUID,
    wp_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """分页获取快照列表（按 created_at DESC）。"""
    await _validate_workpaper_belongs_to_project(db, pid, wp_id)

    items, total = await VersionTrailService.list_snapshots(
        db=db,
        workpaper_id=wp_id,
        project_id=pid,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total}


# ─── GET /versions/{vid} — 快照详情 ──────────────────────────────────────────


@router.get("/{vid}", response_model=SnapshotDetail)
async def get_version_detail(
    pid: UUID,
    wp_id: UUID,
    vid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SnapshotDetail:
    """获取快照详情（含 data_json）。"""
    await _validate_workpaper_belongs_to_project(db, pid, wp_id)

    return await VersionTrailService.get_snapshot_detail(
        db=db,
        snapshot_id=vid,
        project_id=pid,
    )


# ─── POST /versions/compare — diff 对比 ──────────────────────────────────────


@router.post("/compare", response_model=DiffResult)
async def compare_versions(
    pid: UUID,
    wp_id: UUID,
    body: CompareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiffResult:
    """计算两个快照间的 field-level diff。"""
    await _validate_workpaper_belongs_to_project(db, pid, wp_id)

    return await VersionTrailService.compute_diff(
        db=db,
        version_a_id=body.version_a_id,
        version_b_id=body.version_b_id,
        project_id=pid,
    )


# ─── POST /versions/{vid}/rollback — 回滚 ────────────────────────────────────


@router.post("/{vid}/rollback", response_model=SnapshotMeta)
async def rollback_version(
    pid: UUID,
    wp_id: UUID,
    vid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SnapshotMeta:
    """回滚到指定快照（仅现场经理及以上）。"""
    # 权限校验：审计助理不允许回滚
    role_value = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if role_value not in _ROLLBACK_ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="仅现场经理及以上可执行回滚")

    await _validate_workpaper_belongs_to_project(db, pid, wp_id)

    result = await VersionTrailService.rollback_to_snapshot(
        db=db,
        project_id=pid,
        workpaper_id=wp_id,
        snapshot_id=vid,
        user_id=current_user.id,
    )
    await db.commit()
    return result
