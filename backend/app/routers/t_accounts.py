"""T型账户 API 路由

- POST   /api/projects/{id}/t-accounts                    — 创建T型账户
- GET    /api/projects/{id}/t-accounts                    — T型账户列表
- GET    /api/projects/{id}/t-accounts/{tid}              — T型账户详情
- POST   /api/projects/{id}/t-accounts/{tid}/entries      — 添加分录
- POST   /api/projects/{id}/t-accounts/{tid}/calculate    — 计算净变动
- POST   /api/projects/{id}/t-accounts/{tid}/reconcile    — 与资产负债表勾稽
- POST   /api/projects/{id}/t-accounts/{tid}/integrate    — 集成到现金流量表
- GET    /api/t-account-templates                         — T型账户模版

Validates: Requirements 10.1-10.6
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.t_account_service import TAccountService

router = APIRouter(tags=["t-accounts"])


class TAccountCreate(BaseModel):
    account_code: str
    account_name: str
    account_type: str = "asset"
    opening_balance: float = 0
    description: str | None = None


class TAccountEntryCreate(BaseModel):
    entry_type: str  # debit / credit
    amount: float
    description: str | None = None
    reference_id: UUID | None = None


class ReconcileRequest(BaseModel):
    bs_opening: float
    bs_closing: float


@router.post("/api/projects/{project_id}/t-accounts")
async def create_t_account(
    project_id: UUID, body: TAccountCreate, db: AsyncSession = Depends(get_db),
):
    svc = TAccountService()
    result = await svc.create_t_account(db, project_id, body.model_dump())
    await db.commit()
    return result


@router.get("/api/projects/{project_id}/t-accounts")
async def list_t_accounts(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = TAccountService()
    return await svc.list_t_accounts(db, project_id)


@router.get("/api/projects/{project_id}/t-accounts/{t_account_id}")
async def get_t_account(
    project_id: UUID, t_account_id: UUID, db: AsyncSession = Depends(get_db),
):
    svc = TAccountService()
    result = await svc.get_t_account(db, t_account_id)
    if not result:
        raise HTTPException(status_code=404, detail="T型账户不存在")
    return result


@router.post("/api/projects/{project_id}/t-accounts/{t_account_id}/entries")
async def add_entry(
    project_id: UUID, t_account_id: UUID, body: TAccountEntryCreate,
    db: AsyncSession = Depends(get_db),
):
    svc = TAccountService()
    try:
        result = await svc.add_entry(db, t_account_id, body.model_dump())
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/projects/{project_id}/t-accounts/{t_account_id}/calculate")
async def calculate_net_change(
    project_id: UUID, t_account_id: UUID, db: AsyncSession = Depends(get_db),
):
    svc = TAccountService()
    try:
        return await svc.calculate_net_change(db, t_account_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/projects/{project_id}/t-accounts/{t_account_id}/reconcile")
async def reconcile(
    project_id: UUID, t_account_id: UUID, body: ReconcileRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = TAccountService()
    try:
        return await svc.reconcile_with_balance_sheet(
            db, t_account_id,
            Decimal(str(body.bs_opening)), Decimal(str(body.bs_closing)),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/projects/{project_id}/t-accounts/{t_account_id}/integrate")
async def integrate_to_cfs(
    project_id: UUID, t_account_id: UUID, db: AsyncSession = Depends(get_db),
):
    svc = TAccountService()
    try:
        return await svc.integrate_to_cfs(db, t_account_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/t-account-templates")
async def get_templates():
    svc = TAccountService()
    return svc.get_templates()
