"""PBC 清单路由 — wp-evidence-collection spec

CRUD + 状态流转 + 逾期催收
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.collaboration_schemas import PBCItemCreate, PBCItemUpdate
from app.services.pbc_service import pbc_service

router = APIRouter(prefix="/projects/{project_id}/pbc", tags=["PBC清单"])


@router.get("")
async def list_pbc(
    project_id: str,
    status: Optional[str] = Query(None, description="按状态筛选"),
    cycle_code: Optional[str] = Query(None, description="按审计循环筛选"),
    wp_id: Optional[str] = Query(None, description="按底稿筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取项目 PBC 清单"""
    return await pbc_service.list_items(
        db,
        uuid.UUID(project_id),
        status=status,
        cycle_code=cycle_code,
        wp_id=uuid.UUID(wp_id) if wp_id else None,
        page=page,
        page_size=page_size,
    )


@router.post("")
async def create_pbc(
    project_id: str,
    body: PBCItemCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """创建 PBC 项"""
    result = await pbc_service.create_item(
        db,
        uuid.UUID(project_id),
        item_name=body.item_name,
        category=body.category,
        wp_id=uuid.UUID(body.wp_id) if body.wp_id else None,
        cycle_code=body.cycle_code,
        due_date=body.due_date,
        requested_date=body.requested_date,
        requested_by=user.id,
        notes=body.notes,
    )
    await db.commit()
    return result


@router.put("/{item_id}")
async def update_pbc(
    project_id: str,
    item_id: str,
    body: PBCItemUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """更新 PBC 项"""
    update_data = body.model_dump(exclude_unset=True)
    # 转换 wp_id 字符串为 UUID
    if "wp_id" in update_data and update_data["wp_id"]:
        update_data["wp_id"] = uuid.UUID(update_data["wp_id"])

    result = await pbc_service.update_item(db, uuid.UUID(item_id), **update_data)
    if not result:
        raise HTTPException(status_code=404, detail={"message": "PBC 项不存在"})
    await db.commit()
    return result


@router.delete("/{item_id}")
async def delete_pbc(
    project_id: str,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """删除 PBC 项"""
    success = await pbc_service.delete_item(db, uuid.UUID(item_id))
    if not success:
        raise HTTPException(status_code=404, detail={"message": "PBC 项不存在"})
    await db.commit()
    return {"success": True}


@router.post("/{item_id}/receive")
async def receive_pbc(
    project_id: str,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """标记 PBC 项已收到（pending→received）"""
    result = await pbc_service.receive_item(db, uuid.UUID(item_id), user.id)
    if not result:
        raise HTTPException(status_code=404, detail={"message": "PBC 项不存在"})
    await db.commit()
    return result


@router.get("/by-workpaper/{wp_id}")
async def get_pbc_by_workpaper(
    project_id: str,
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取底稿关联的 PBC 项（侧栏证据收集 tab 用）"""
    return await pbc_service.get_items_by_workpaper(db, uuid.UUID(wp_id))


@router.post("/check-overdue")
async def check_overdue(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """检测逾期 PBC 项并自动建 IssueTicket"""
    tickets = await pbc_service.create_overdue_tickets(
        db, uuid.UUID(project_id), user.id
    )
    await db.commit()
    return {"tickets_created": len(tickets), "tickets": tickets}
