"""本项目 EQCR 判定 —— EQCR 只读排除的唯一判定。

用途：
- ``is_project_eqcr``：附注编辑门禁、交付中心门禁与附注可编辑判定查询都经它得出「是否本项目 EQCR」，
  门禁内不另查委派角色，也不另比较全局角色（需求 7.3）。
- ``project_eqcr_user_ids``：连续审计复制团队时跳过上年项目的 EQCR（需求 11.1）。
- EQCR 本人的正向授权（审批、意见解锁、备忘录定稿、工时等）仍用
  ``EqcrWorkbenchService._is_user_eqcr_on``，不在本模块（需求 7.7）。

判定口径（需求 7.1）：
- 本项目 EQCR ⇔ 全局角色为 eqcr ∨ 在本项目至少有一条 EQCR 别名现行委派；admin 不豁免。
- 现行委派：``project_assignments`` 未删除，经未删除、``user_id`` 非空的 ``staff_members`` 关联到用户；
  同一用户经多条人员库记录持有多条委派时，任一条命中即算。
- 委派角色按字符串精确匹配属于 ``EQCR_ROLE_ALIASES``（由 ``ROLE_MAP`` 推导，本模块不另存别名，需求 7.2）；
  大小写不同或带首尾空白的变体不算。
- 只看本项目；不 JOIN projects / users / project_users ⇒ 项目软删、人员状态、成员行的项目角色与级别都不影响结论。
- ``project_eqcr_user_ids`` 只按委派条件取人：全局角色为 eqcr、在该项目没有 EQCR 别名委派的用户不在其中。

出错语义（需求 7.6）：不经任何缓存，每次直接查库；不 ``try/except`` —— 查询异常原样冒泡，
调用方的请求失败、业务一次也不执行，不按「非 EQCR」放行。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import UserRole
from app.models.core import User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.assignment_service import EQCR_ROLE_ALIASES


def _eqcr_assignment_conditions(project_id: UUID) -> tuple[ColumnElement[bool], ...]:
    """项目 P 上「EQCR 别名现行委派」的 WHERE 条件；两个查询共用，委派口径只写这一处。

    调用方须以 ``ProjectAssignment.staff_id == StaffMember.id`` 内连接人员库表。
    """
    return (
        ProjectAssignment.project_id == project_id,
        ProjectAssignment.role.in_(sorted(EQCR_ROLE_ALIASES)),  # 精确匹配：不转小写、不去空白
        ProjectAssignment.is_deleted == False,  # noqa: E712
        StaffMember.is_deleted == False,  # noqa: E712
        StaffMember.user_id.is_not(None),
    )


async def is_project_eqcr(db: AsyncSession, user: User, project_id: UUID) -> bool:
    """本项目 EQCR ⇔ 全局角色为 eqcr ∨ 本项目有 EQCR 别名现行委派（需求 7.1）。不经缓存；出错直接抛。"""
    if user.role.value == UserRole.eqcr.value:
        return True
    # 经模块全局名调用下层取数点：测试替换与故障注入都落在这一层，不替换本函数。
    return await _count_project_eqcr_assignments(db, user.id, project_id) > 0


async def _count_project_eqcr_assignments(db: AsyncSession, user_id: UUID, project_id: UUID) -> int:
    """该用户在项目 P 的 EQCR 别名现行委派条数。

    下层取数点：测试只在「不观测 EQCR」的用例里替换它，故障注入也注在这里。
    """
    q = (
        select(func.count(ProjectAssignment.id))
        .select_from(ProjectAssignment)
        .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
        .where(*_eqcr_assignment_conditions(project_id), StaffMember.user_id == user_id)
    )
    return int((await db.execute(q)).scalar() or 0)


async def project_eqcr_user_ids(db: AsyncSession, project_id: UUID) -> set[UUID]:
    """在项目 P 持有 EQCR 别名现行委派的用户集合（连续审计复制团队用；与上式同一委派口径，不含全局角色分支）。"""
    q = (
        select(StaffMember.user_id)
        .select_from(ProjectAssignment)
        .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
        .where(*_eqcr_assignment_conditions(project_id))
    )
    return set((await db.execute(q)).scalars().all())
