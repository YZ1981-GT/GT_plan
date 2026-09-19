"""程序行任务查询 API（Task 12，Design C11 / API section / F1）

Feature: procedure-delegation-notification / 需求 9.1-9.8, 12.3, 14.3-14.4

端点（**全部严格只读**，架构守卫 GET 禁写）：
- ``GET /api/projects/{project_id}/procedure-row-tasks``：项目级"我的程序任务"分页查询。
- ``GET /api/my/procedure-row-tasks``：跨项目"我的程序任务"分页查询。
- ``GET /api/projects/{project_id}/procedure-row-tasks/{task_id}``：单任务详情 + 深链定位 key。

查询以当前 user → active staff ids 为入口，按 assignee/reviewer covering index 过滤
（Design C11）。详情端点从服务端反查 task→project 绑定并校验参与关系；跨项目/未授权
返回 404/403 且不泄露程序文本（需求 9.8 / Property P28）。

注意：这些是 **纯读** GET 路径，绝不触发物化/写入（需求 2.5）。service 只 SELECT。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.procedure_authorization import (
    ParticipantAccess,
    resolve_task_participant_access,
)
from app.services.procedure_task_query_service import (
    ProcedureTaskQueryService,
    TaskQueryFilters,
)

# 项目级查询 + 详情（与 command router 同前缀，FastAPI 允许多 router 共享 prefix）。
project_query_router = APIRouter(prefix="/api/projects", tags=["procedure-row-tasks"])
# 跨项目 "我的程序任务"。
my_query_router = APIRouter(prefix="/api/my", tags=["procedure-row-tasks"])


def _parse_filters(
    *,
    project_id: UUID | None,
    cycle: str | None,
    wp_index_id: UUID | None,
    workflow_status: str | None,
    role: str | None,
    overdue_only: bool,
    page: int,
    page_size: int,
) -> TaskQueryFilters:
    if role is not None and role not in ("assignee", "reviewer"):
        raise HTTPException(status_code=422, detail="role 仅支持 assignee/reviewer")
    return TaskQueryFilters(
        project_id=project_id,
        cycle=cycle,
        wp_index_id=wp_index_id,
        workflow_status=workflow_status,
        role=role,
        overdue_only=overdue_only,
        page=page,
        page_size=page_size,
    )


@project_query_router.get("/{project_id}/procedure-row-tasks")
async def list_project_row_tasks(
    project_id: UUID,
    cycle: str | None = Query(None),
    wp_index_id: UUID | None = Query(None),
    workflow_status: str | None = Query(None),
    role: str | None = Query(None, description="assignee=我执行的 / reviewer=我复核的"),
    overdue_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """项目级"我的程序任务"分页查询（当前 user 的 assignee/reviewer 任务，纯读）。"""
    svc = ProcedureTaskQueryService(db)
    filters = _parse_filters(
        project_id=project_id, cycle=cycle, wp_index_id=wp_index_id,
        workflow_status=workflow_status, role=role, overdue_only=overdue_only,
        page=page, page_size=page_size,
    )
    return await svc.list_tasks(user.id, filters)


@my_query_router.get("/procedure-row-tasks")
async def list_my_row_tasks(
    project_id: UUID | None = Query(None),
    cycle: str | None = Query(None),
    wp_index_id: UUID | None = Query(None),
    workflow_status: str | None = Query(None),
    role: str | None = Query(None, description="assignee=我执行的 / reviewer=我复核的"),
    overdue_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """跨项目"我的程序任务"分页查询（可选 project 收窄，纯读）。"""
    svc = ProcedureTaskQueryService(db)
    filters = _parse_filters(
        project_id=project_id, cycle=cycle, wp_index_id=wp_index_id,
        workflow_status=workflow_status, role=role, overdue_only=overdue_only,
        page=page, page_size=page_size,
    )
    return await svc.list_tasks(user.id, filters)


@project_query_router.get("/{project_id}/procedure-row-tasks/{task_id}")
async def get_row_task_detail(
    project_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """单任务详情（纯读）。

    - 校验 task→project 绑定；跨项目/不存在 → 404，不泄露程序文本（需求 9.8 / P28）。
    - 校验参与关系（delegator/assignee/reviewer/历史只读）；无任何访问 → 404（不泄露）。
    - 返回 nullable wp_id + materialization_required + 深链定位 key（sheet_key+definition_key）。
    """
    from app.routers._wp_gate import enforce_task_gate

    # Wp_Bound_Gate（task 绑定）：读取程序行任务详情正文之前完成可见性/绑定判定
    # （Req 8.12 / procedure_task 入口族）。gate 从 task 反查 project + 唯一 wp_index，
    # row-only 身份只授权映射 sheet；跨项目/out-of-scope/未委派统一 External_Not_Found（404）。
    # read_task 属只读族，全部参与身份（lead/assignee/reviewer/history）均可命中，作为
    # 统一门可见性前置；更细粒度的参与者动作授权仍由 procedure_authorization 原生强制。
    await enforce_task_gate(
        db, user,
        entrypoint="procedure.task_read", action="read_task", method="GET",
        task_id=task_id, project_id=project_id, entry_family="procedure_task",
        route_name="/api/projects/{project_id}/procedure-row-tasks/{task_id}",
    )

    svc = ProcedureTaskQueryService(db)
    task = await svc.get_detail(project_id, task_id)
    if task is None:
        # 不存在或跨项目：统一 404，不泄露跨项目对象文本
        raise HTTPException(status_code=404, detail="任务不存在")

    # 参与关系授权（从服务端对象反查 project binding，不信任客户端）
    resolution = await resolve_task_participant_access(db, task_id, user)
    if resolution.access == ParticipantAccess.none:
        # 认证用户但对该任务无任何访问：404 不泄露程序文本
        raise HTTPException(status_code=404, detail="任务不存在")

    staff_ids = set(await svc.active_staff_ids(user.id))
    detail = svc.serialize_detail(task, staff_ids=staff_ids)
    detail["access"] = resolution.access.value
    return detail
