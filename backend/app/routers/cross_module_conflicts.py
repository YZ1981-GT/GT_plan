"""跨模块冲突 router — V3 收官增强 Req 7.4

提供调解面板使用的 4 个端点：

- GET  /api/projects/{pid}/conflicts/pending      列出 pending 冲突 + 计数
- GET  /api/projects/{pid}/conflicts              列出冲突（按 status/target_module 过滤 + 分页）
- POST /api/conflicts/{conflict_id}/resolve       用户调解（keep_manual / accept_new / merge）

底层调用 conflict_resolution_service（7.1 已就位）。

Validates: Requirements 7.4
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services import conflict_resolution_service as svc

router = APIRouter(tags=["跨模块冲突调解"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ResolveRequest(BaseModel):
    resolution: str  # 'keep_manual' | 'accept_new' | 'merge'
    merge_value: str | None = None


def _serialize(c) -> dict:
    """将 CrossModuleConflict ORM 对象序列化为前端所需的字典。"""
    return {
        "id": str(c.id),
        "project_id": str(c.project_id),
        "source_module": c.source_module,
        "source_id": str(c.source_id),
        "target_module": c.target_module,
        "target_id": str(c.target_id),
        "target_field": c.target_field,
        "upstream_value": c.upstream_value,
        "manual_value": c.manual_value,
        "final_value": c.final_value,
        "resolution": c.resolution,
        "resolved_by": str(c.resolved_by) if c.resolved_by else None,
        "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/conflicts/pending
# ---------------------------------------------------------------------------


@router.get("/api/projects/{project_id}/conflicts/pending")
async def list_pending(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """返回项目下未调解（status='pending'）的冲突列表 + 总数。"""
    items = await svc.list_pending(db=db, project_id=project_id, limit=limit)
    count = await svc.count_pending(db=db, project_id=project_id)
    return {
        "count": count,
        "items": [_serialize(c) for c in items],
    }


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/conflicts
# ---------------------------------------------------------------------------


@router.get("/api/projects/{project_id}/conflicts")
async def list_conflicts(
    project_id: UUID,
    status: str | None = Query(None),
    target_module: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """按项目列出冲突记录，可选 status / target_module 过滤 + 分页。"""
    try:
        items = await svc.list_by_project(
            db=db,
            project_id=project_id,
            status=status,
            target_module=target_module,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "items": [_serialize(c) for c in items],
    }


# ---------------------------------------------------------------------------
# POST /api/conflicts/{conflict_id}/resolve
# ---------------------------------------------------------------------------


@router.post("/api/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: UUID,
    payload: ResolveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """用户调解一条 pending 冲突（keep_manual / accept_new / merge）。"""
    if payload.resolution not in {"keep_manual", "accept_new", "merge"}:
        raise HTTPException(
            status_code=400,
            detail="resolution 必须是 keep_manual / accept_new / merge",
        )
    try:
        c = await svc.resolve(
            db=db,
            conflict_id=conflict_id,
            user_id=user.id,
            resolution=payload.resolution,
            merge_value=payload.merge_value,
        )
        await db.commit()
        return {
            "id": str(c.id),
            "status": c.status,
            "resolution": c.resolution,
            "final_value": c.final_value,
        }
    except svc.ConflictNotFoundError:
        raise HTTPException(status_code=404, detail="冲突记录不存在")
    except svc.ConflictAlreadyResolvedError:
        raise HTTPException(status_code=422, detail="冲突已调解过，不可重复操作")
    except svc.ConflictMergeValueRequiredError:
        raise HTTPException(status_code=400, detail="merge 决议必须提供 merge_value")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
