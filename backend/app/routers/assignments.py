"""团队委派 API 路由

Phase 9 Task 1.4
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.staff_schemas import AssignmentBatchRequest, AssignmentResponse
from app.services.assignment_service import AssignmentService

router = APIRouter(prefix="/api/projects", tags=["assignments"])


# ⚠ /my/assignments 必须在 /{project_id}/assignments 之前，
# 否则 FastAPI 会把 "my" 当成 UUID 类型的 project_id 导致 422
@router.get("/my/assignments")
async def my_assignments(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取当前用户被委派的项目列表"""
    svc = AssignmentService(db)
    return await svc.get_my_assignments(user.id)


@router.get("/{project_id}/assignments")
async def list_assignments(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = AssignmentService(db)
    return await svc.list_assignments(project_id)


@router.post("/{project_id}/assignments")
async def save_assignments(
    project_id: UUID,
    data: AssignmentBatchRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    # R5 任务 2：捕获 EQCR 独立性等 SOD 违规，转 409 返回
    from app.services.sod_guard_service import SodViolation

    svc = AssignmentService(db)
    assignments = [a.model_dump() for a in data.assignments]
    try:
        created = await svc.save_assignments(
            project_id, assignments, assigned_by=user.id if user else None
        )
    except SodViolation as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": exc.policy_code,
                "message": exc.message,
            },
        )
    await db.commit()

    # 委派落库后失效程序表 auto_data 缓存（A1 看板 review_dashboard_status 读
    # project_assignments 取五级复核人员姓名，TTL 30s 内会显示旧人员）。
    # 🔴 修复前靠 save_assignments 冒充 DATA_IMPORTED 顺带清缓存；去掉伪事件后
    #    必须显式失效，否则委派后看板仍显示旧复核人。放在 commit 之后：
    #    commit 失败则不失效（缓存仍与库一致），不会出现「缓存已清、库未变」。
    from app.services.procedure_table_auto_service import invalidate_auto_cache

    invalidate_auto_cache(project_id)
    return {
        "message": f"已委派 {len(created)} 名成员",
        "count": len(created),
    }
