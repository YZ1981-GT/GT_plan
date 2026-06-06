"""函证管理路由

能力域 D — global-refinement-v5-closure：
完整 CRUD + 状态机推进端点。
router 统一 commit（项目铁律）。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services import confirmation_service

router = APIRouter(prefix="/projects/{project_id}/confirmations", tags=["函证管理"])


# ─── Request / Response schemas ────────────────────────────────────────────


class ConfirmationCreate(BaseModel):
    confirm_type: str = Field(..., description="函证类型: receivable/payable/bank/loan")
    counterparty: str = Field(..., description="函证对象名称")
    wp_id: str | None = None
    account_code: str | None = None
    book_amount: float | None = None
    confirmed_amount: float | None = None
    diff_amount: float | None = None
    diff_note: str | None = None


class ConfirmationUpdate(BaseModel):
    confirm_type: str | None = None
    counterparty: str | None = None
    wp_id: str | None = None
    account_code: str | None = None
    book_amount: float | None = None
    confirmed_amount: float | None = None
    diff_amount: float | None = None
    diff_note: str | None = None


class TransitionRequest(BaseModel):
    target_status: str = Field(..., description="目标状态")


# ─── Endpoints ─────────────────────────────────────────────────────────────


@router.get("")
async def list_confirmations(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取项目函证列表"""
    pid = uuid.UUID(project_id)
    items = await confirmation_service.list_confirmations(db, pid)
    await db.commit()
    return {"items": items, "total": len(items)}


@router.post("")
async def create_confirmation(
    project_id: str,
    body: ConfirmationCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """创建函证"""
    pid = uuid.UUID(project_id)
    data = body.model_dump()
    data["created_by"] = user.id if hasattr(user, "id") else None
    result = await confirmation_service.create_confirmation(db, pid, data)
    await db.commit()
    return result


@router.get("/{confirmation_id}")
async def get_confirmation(
    project_id: str,
    confirmation_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取函证详情"""
    cid = uuid.UUID(confirmation_id)
    try:
        result = await confirmation_service.get_confirmation(db, cid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return result


@router.put("/{confirmation_id}")
async def update_confirmation(
    project_id: str,
    confirmation_id: str,
    body: ConfirmationUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """更新函证"""
    cid = uuid.UUID(confirmation_id)
    data = body.model_dump(exclude_unset=True)
    try:
        result = await confirmation_service.update_confirmation(db, cid, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return result


@router.delete("/{confirmation_id}")
async def delete_confirmation(
    project_id: str,
    confirmation_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """删除函证"""
    cid = uuid.UUID(confirmation_id)
    try:
        result = await confirmation_service.delete_confirmation(db, cid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return result


@router.post("/{confirmation_id}/transition")
async def transition_confirmation(
    project_id: str,
    confirmation_id: str,
    body: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """状态推进"""
    cid = uuid.UUID(confirmation_id)
    try:
        result = await confirmation_service.transition_status(db, cid, body.target_status)
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    await db.commit()
    return result
