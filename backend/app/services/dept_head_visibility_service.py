"""部门负责人项目可见集 —— 单一真源。

需求：部门负责人（``sys_dept.head_id`` 指向的用户）能看见「本部门下的所有项目」。

项目表 ``projects`` 没有部门列，部门与项目唯一的关联是「用户的部门」（``users.dept_id``）。
故「本部门下的项目」= 本部门（含子部门）成员参与的项目，成员口径取并集：
项目的创建人 / 经理 / 签字合伙人 / ``project_users`` 成员行，只要其 ``dept_id``
属于负责人所负责的部门集合即算。

- 「本部门」含其**子部门**（``sys_dept.parent_id`` 递归）：上级部门负责人能看下级部门项目。
- 本函数**不判系统角色**：谁是某部门的 ``head_id`` 谁就按此可见，与合伙人可见集相互独立、并集使用。
- 均限未删除项目。

依赖方向单向：本模块只依赖 ``app.models``，不导入 ``app.deps``。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Department, Project, ProjectUser, User

__all__ = ["headed_department_ids", "dept_member_ids", "dept_head_visible_project_ids"]


async def headed_department_ids(user_id: UUID, db: AsyncSession) -> set[UUID]:
    """用户直接负责的部门 + 其所有子孙部门 id（未删除）。

    BFS 逐层下探 ``parent_id``（而非递归 CTE），SQLite 测试 dialect 也能跑。
    """
    roots = (
        await db.execute(
            select(Department.id).where(
                Department.head_id == user_id,
                Department.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().all()
    result: set[UUID] = set(roots)
    frontier = set(roots)
    while frontier:
        children = (
            await db.execute(
                select(Department.id).where(
                    Department.parent_id.in_(frontier),
                    Department.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
        new = {c for c in children if c not in result}
        if not new:
            break
        result.update(new)
        frontier = new
    return result


async def dept_member_ids(dept_ids: set[UUID], db: AsyncSession) -> set[UUID]:
    """部门集合内的全部未删除用户 id。"""
    if not dept_ids:
        return set()
    rows = (
        await db.execute(
            select(User.id).where(
                User.dept_id.in_(dept_ids),
                User.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().all()
    return set(rows)


async def dept_head_visible_project_ids(user: User, db: AsyncSession) -> set[UUID]:
    """部门负责人可见项目集。非部门负责人（无 headed 部门）返回空集。"""
    dept_ids = await headed_department_ids(user.id, db)
    if not dept_ids:
        return set()

    member_ids = await dept_member_ids(dept_ids, db)
    if not member_ids:
        return set()

    visible: set[UUID] = set()

    # (1) 部门成员为创建人 / 经理 / 签字合伙人的项目
    visible.update(
        (
            await db.execute(
                select(Project.id).where(
                    or_(
                        Project.created_by.in_(member_ids),
                        Project.manager_id.in_(member_ids),
                        Project.partner_id.in_(member_ids),
                    ),
                    Project.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
    )

    # (2) 部门成员在 project_users 有未删除成员行的项目
    visible.update(
        (
            await db.execute(
                select(ProjectUser.project_id)
                .join(Project, Project.id == ProjectUser.project_id)
                .where(
                    ProjectUser.user_id.in_(member_ids),
                    ProjectUser.is_deleted == False,  # noqa: E712
                    Project.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
    )

    return visible
