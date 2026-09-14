"""程序行任务查询服务（Task 12，Design C11）

Feature: procedure-delegation-notification
需求：9.1-9.8（任务查询、深链、现有页面重构）、12.3（跨项目 covering index）、14.3-14.4
Design：C11（ProcedureTaskQueryService）、F1（MyProcedureTasks.vue）
Properties：P27（due_at 逾期谓词）、P28（深链与项目边界）

职责（**纯读**，无任何写副作用；GET/render 路径专用）：

- ``active_staff_ids(user_id)``：当前 user → active StaffMember.id 集合（宽松，可为空；
  不像 Delegator guard 要求唯一，查询按 assignee/reviewer covering index 过滤）。
- ``list_tasks(...)``：项目级 / 跨项目 "我的程序任务" 分页查询，按 active staff 的
  assignee/reviewer covering index 过滤；支持 project、cycle、wp_index、workflow、role
  （我执行的/我复核的）、overdue 状态筛选。
- ``get_detail(project_id, task_id)``：单任务详情，返回 nullable wp_id 与
  materialization_required；**深链不接受 program_no fallback**（按 sheet_key+definition_key）。

overdue 谓词（需求 9.3 / P27）：仅当 ``due_at IS NOT NULL`` 且 workflow 非 reviewed/cancelled
且 ``now > due_at`` 时为 true；due_at 为空 **永不** 逾期。

约定：本模块只 SELECT，绝不写库（架构守卫 GET 禁写）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureRowTask
from app.models.staff_models import StaffMember

# 已完成/已取消：overdue 谓词排除的终态/完结态（需求 9.3）。
_OVERDUE_EXCLUDED_STATES = frozenset({"reviewed", "cancelled"})

# 委派角色过滤（我执行的 / 我复核的）。
ROLE_ASSIGNEE = "assignee"
ROLE_REVIEWER = "reviewer"

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_overdue(
    due_at: datetime | None,
    workflow_status: str | None,
    now: datetime | None = None,
) -> bool:
    """逾期谓词纯函数（需求 9.3 / Property P27）。

    仅当 ``due_at`` 非空、workflow 非 reviewed/cancelled 且当前时间晚于 due_at 时为 true。
    due_at 为空 **永不** 逾期。
    """
    if due_at is None:
        return False
    if (workflow_status or "") in _OVERDUE_EXCLUDED_STATES:
        return False
    now = now or _utcnow()
    # 兼容 naive/aware 比较：统一到 aware（naive 视为 UTC）。
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now > due_at


@dataclass
class TaskQueryFilters:
    """任务查询筛选条件（全部可选）。"""

    project_id: UUID | None = None
    cycle: str | None = None
    wp_index_id: UUID | None = None
    workflow_status: str | None = None
    role: str | None = None  # assignee | reviewer | None（两者并集）
    overdue_only: bool = False
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE


def _serialize_task(task: ProcedureRowTask, *, staff_ids: set[UUID], now: datetime) -> dict:
    """把 task 序列化为查询结果行（Req 9.2 字段集 + overdue + materialization_required）。"""
    assignee = task.assignee_staff_id
    reviewer = task.reviewer_staff_id
    my_role: str | None = None
    if assignee is not None and assignee in staff_ids:
        my_role = ROLE_ASSIGNEE
    elif reviewer is not None and reviewer in staff_ids:
        my_role = ROLE_REVIEWER
    return {
        "task_id": str(task.id),
        "project_id": str(task.project_id),
        "wp_index_id": str(task.wp_index_id),
        "wp_id": str(task.wp_id) if task.wp_id else None,
        "definition_key": task.definition_key,
        "sheet_key": task.sheet_key,
        "wp_code": task.wp_code,
        "sheet_name": task.sheet_name,
        "program_no": task.program_no,
        "procedure_text": task.procedure_text,
        "audit_cycle_snapshot": task.audit_cycle_snapshot,
        "applicability_status": task.applicability_status,
        "workflow_status": task.workflow_status,
        "assignee_staff_id": str(assignee) if assignee else None,
        "reviewer_staff_id": str(reviewer) if reviewer else None,
        "assignment_version": task.assignment_version,
        "lock_version": task.lock_version,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "overdue": compute_overdue(task.due_at, task.workflow_status, now),
        # 已物化任务：materialization_required 恒为 false（未物化行只在 render overlay 出现）。
        "materialization_required": False,
        "my_role": my_role,
        "created_at": task.created_at.isoformat() if getattr(task, "created_at", None) else None,
        "updated_at": task.updated_at.isoformat() if getattr(task, "updated_at", None) else None,
    }


class ProcedureTaskQueryService:
    """程序行任务查询（纯读）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def active_staff_ids(self, user_id: UUID) -> list[UUID]:
        """当前 user → active StaffMember.id 集合（宽松，可为空）。"""
        rows = (
            await self.db.execute(
                sa.select(StaffMember.id).where(
                    StaffMember.user_id == user_id,
                    StaffMember.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
        return list(rows)

    def _role_predicate(self, staff_ids: list[UUID], role: str | None):
        """按 role 构造 assignee/reviewer 过滤谓词（走对应 covering index）。"""
        assignee_pred = ProcedureRowTask.assignee_staff_id.in_(staff_ids)
        reviewer_pred = ProcedureRowTask.reviewer_staff_id.in_(staff_ids)
        if role == ROLE_ASSIGNEE:
            return assignee_pred
        if role == ROLE_REVIEWER:
            return reviewer_pred
        return sa.or_(assignee_pred, reviewer_pred)

    async def list_tasks(self, user_id: UUID, filters: TaskQueryFilters) -> dict:
        """分页查询当前 user 的程序任务（我执行的/我复核的）。

        返回 ``{items, pagination: {page, page_size, total, total_pages}}``。
        无 active staff 或无匹配任务时返回空页（不泄露、不报错）。
        """
        staff_ids = await self.active_staff_ids(user_id)
        page = max(1, filters.page)
        page_size = min(max(1, filters.page_size), MAX_PAGE_SIZE)
        empty = {
            "items": [],
            "pagination": {"page": page, "page_size": page_size, "total": 0, "total_pages": 0},
        }
        if not staff_ids:
            return empty

        conds = [
            ProcedureRowTask.is_deleted == sa.false(),
            self._role_predicate(staff_ids, filters.role),
        ]
        if filters.project_id is not None:
            conds.append(ProcedureRowTask.project_id == filters.project_id)
        if filters.cycle:
            conds.append(ProcedureRowTask.audit_cycle_snapshot == filters.cycle)
        if filters.wp_index_id is not None:
            conds.append(ProcedureRowTask.wp_index_id == filters.wp_index_id)
        if filters.workflow_status:
            conds.append(ProcedureRowTask.workflow_status == filters.workflow_status)

        now = _utcnow()
        # overdue 在 SQL 侧收窄（due_at 非空、非完结态、已过期）；覆盖 covering index due_at 列。
        if filters.overdue_only:
            conds.append(ProcedureRowTask.due_at.isnot(None))
            conds.append(ProcedureRowTask.workflow_status.notin_(list(_OVERDUE_EXCLUDED_STATES)))
            conds.append(ProcedureRowTask.due_at < now)

        total = (
            await self.db.execute(
                sa.select(sa.func.count()).select_from(ProcedureRowTask).where(*conds)
            )
        ).scalar() or 0

        rows = (
            await self.db.execute(
                sa.select(ProcedureRowTask)
                .where(*conds)
                .order_by(
                    # 逾期/临期优先：due_at 升序（NULL 最后），再按更新时间倒序稳定分页
                    ProcedureRowTask.due_at.asc().nullslast(),
                    ProcedureRowTask.updated_at.desc(),
                    ProcedureRowTask.id.asc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        staff_set = set(staff_ids)
        items = [_serialize_task(t, staff_ids=staff_set, now=now) for t in rows]
        total_pages = (total + page_size - 1) // page_size
        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": int(total),
                "total_pages": int(total_pages),
            },
        }

    async def get_detail(self, project_id: UUID, task_id: UUID) -> ProcedureRowTask | None:
        """按 task→project 绑定取单任务（跨项目返回 None，交路由处理 404）。"""
        return (
            await self.db.execute(
                sa.select(ProcedureRowTask).where(
                    ProcedureRowTask.id == task_id,
                    ProcedureRowTask.project_id == project_id,
                    ProcedureRowTask.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()

    def serialize_detail(self, task: ProcedureRowTask, *, staff_ids: set[UUID] | None = None) -> dict:
        """详情序列化（含 nullable wp_id、materialization_required、深链定位 key）。"""
        return _serialize_task(task, staff_ids=staff_ids or set(), now=_utcnow())
