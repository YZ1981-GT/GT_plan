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

🔴 鉴权与项目隔离（2026-09-28 重修）
-----------------------------------
修复前状态（两层缺陷叠加）：

1. **仅登录不校项目** —— 8 个端点里 7 个挂 `get_current_user`（只保证登录）、
   1 个（`list`）连这个都没有。`get_current_user` **不含项目维度** ⇒ 任何登录
   用户（含 readonly 外部人员）可访问任意项目。
2. **`project_id` 是装饰** —— service 层 5 个方法全不按 `project_id` 过滤，
   router 也不把它传下去 ⇒ 即便加了项目级门禁，校验的也是**无关对象**
   （`disclosure_notes.py` 的注释早已警告过这一形态：「调用方可以传一个自己
   有权的项目，却对另一个项目的对象动手」）。`add_entry` 更是**写路径**，
   可往他人项目的账户塞分录。

本表**不在 RLS 覆盖范围**（`V005__enable_rls.sql` 只保护 working_paper /
adjustments / tb_balance / review_records；真实 PG 现查 217 张带 project_id
的表里仅 3 张受保护）⇒ 没有 DB 层兜底，隔离必须在 service 层做。

修复 = 两层同时补：
  · 门禁：`require_project_access("readonly")` 读 / `("edit")` 写
    （替换原 `get_current_user`，对齐 `disclosure_notes` 的分档）
  · 隔离：所有 service 调用**显式传 `project_id`**，归属不符按 404 处理
    （不透露对象是否存在）

⚠️ 这是**权限收紧**：此前任何登录用户可读写任意项目的 T 型账户，
现需对该项目有 readonly / edit 权限。
守卫：`tests/test_t_account_project_isolation.py`。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
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
    current_user: User = Depends(require_project_access("edit")),
):
    svc = TAccountService()
    result = await svc.create_t_account(
        db, project_id, body.model_dump(), created_by=current_user.id
    )
    await db.commit()
    return result


@router.get("/api/projects/{project_id}/t-accounts")
async def list_t_accounts(
    project_id: UUID, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    svc = TAccountService()
    return await svc.list_t_accounts(db, project_id)


@router.get("/api/projects/{project_id}/t-accounts/{t_account_id}")
async def get_t_account(
    project_id: UUID, t_account_id: UUID, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    svc = TAccountService()
    result = await svc.get_t_account(db, t_account_id, project_id=project_id)
    if not result:
        # 归属不符与真不存在同样返回 404：不透露他人项目对象的存在性
        raise HTTPException(status_code=404, detail="T型账户不存在")
    return result


@router.post("/api/projects/{project_id}/t-accounts/{t_account_id}/entries")
async def add_entry(
    project_id: UUID, t_account_id: UUID, body: TAccountEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    svc = TAccountService()
    try:
        result = await svc.add_entry(
            db, t_account_id, body.model_dump(), project_id=project_id
        )
        await db.commit()
        return result
    except ValueError as e:
        # 归属校验失败走 404（"T型账户不存在"），入参校验失败走 400
        if "不存在" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/projects/{project_id}/t-accounts/{t_account_id}/calculate")
async def calculate_net_change(
    project_id: UUID, t_account_id: UUID, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    svc = TAccountService()
    try:
        return await svc.calculate_net_change(db, t_account_id, project_id=project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/projects/{project_id}/t-accounts/{t_account_id}/reconcile")
async def reconcile(
    project_id: UUID, t_account_id: UUID, body: ReconcileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    svc = TAccountService()
    try:
        return await svc.reconcile_with_balance_sheet(
            db, t_account_id,
            Decimal(str(body.bs_opening)), Decimal(str(body.bs_closing)),
            project_id=project_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/projects/{project_id}/t-accounts/{t_account_id}/integrate")
async def integrate_to_cfs(
    project_id: UUID, t_account_id: UUID, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    svc = TAccountService()
    try:
        return await svc.integrate_to_cfs(db, t_account_id, project_id=project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/t-account-templates")
async def get_templates():
    """静态模版清单（不含任何项目数据，无需项目鉴权）。"""
    svc = TAccountService()
    return svc.get_templates()
