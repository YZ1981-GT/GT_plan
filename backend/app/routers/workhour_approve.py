"""工时批量审批路由 — Round 2 需求 7

POST /api/workhours/batch-approve
- 幂等键头 Idempotency-Key
- 状态流转 confirmed→approved 或 confirmed→draft（退回附原因）
- SOD 守卫：审批人 ≠ 被审批人
- 发通知 workhour_approved / workhour_rejected
"""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.services.workhour_approve_service import workhour_approve_service

router = APIRouter(prefix="/api", tags=["workhours"])


class BatchApproveRequest(BaseModel):
    """批量审批请求体"""

    hour_ids: list[UUID] = Field(..., min_length=1, description="工时记录 ID 列表")
    action: Literal["approve", "reject"] = Field(..., description="操作：approve 批准 / reject 退回")
    reason: Optional[str] = Field(None, description="退回原因（reject 时建议填写）")


class BatchApproveFailedItem(BaseModel):
    """审批失败条目"""

    id: str
    reason: str


class BatchApproveResponse(BaseModel):
    """批量审批响应"""

    approved_count: int
    rejected_count: int
    failed: list[BatchApproveFailedItem]


@router.post(
    "/workhours/batch-approve",
    response_model=BatchApproveResponse,
    summary="工时批量审批",
    description="批量批准或退回工时记录。需要 manager 或 admin 角色。",
)
async def batch_approve_workhours(
    body: BatchApproveRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["manager", "admin"])),
):
    """批量审批工时。

    - 幂等键头 `Idempotency-Key` 防止网络抖动导致重复审批
    - 状态流转：confirmed → approved（批准）或 confirmed → draft（退回）
    - SOD 守卫：审批人不能审批自己的工时
    - 审批/退回后自动发通知给员工

    权限（Batch 1 P0.4）：
    - admin：可审批所有项目工时
    - manager：只能审批 project_assignment.role IN ('manager','signing_partner')
      的项目工时；跨项目会返回 403
    """
    # reject 时建议提供原因
    if body.action == "reject" and not body.reason:
        # 不强制，但给默认值
        pass

    # Batch 1 P0.4: 项目级权限校验
    if current_user.role.value != "admin":
        import sqlalchemy as _sa
        from app.models.staff_models import WorkHour as _WH
        from app.services.manager_dashboard_service import ManagerDashboardService

        # 获取 hour_ids 涉及的项目
        proj_ids_stmt = _sa.select(_sa.distinct(_WH.project_id)).where(
            _WH.id.in_(body.hour_ids),
            _WH.is_deleted == _sa.false(),
        )
        hour_project_ids = {
            r[0] for r in (await db.execute(proj_ids_stmt)).all() if r[0] is not None
        }

        if hour_project_ids:
            mgr_svc = ManagerDashboardService(db)
            allowed_ids = set(await mgr_svc._get_manager_project_ids(current_user))
            unauthorized = hour_project_ids - allowed_ids
            if unauthorized:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "权限不足：工时涉及不属于您管理范围的项目 "
                        f"({len(unauthorized)} 个)"
                    ),
                )

    result = await workhour_approve_service.batch_approve(
        db=db,
        hour_ids=body.hour_ids,
        action=body.action,
        approver_user_id=current_user.id,
        reason=body.reason,
        idempotency_key=idempotency_key,
    )

    return result
