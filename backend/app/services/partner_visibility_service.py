"""合伙人项目可见集 —— 单一真源。

合伙人（系统角色 partner）只能看见「自己名下」的项目，不再与 admin 一样看全部。
可见集 = 下面六个来源的并集，全部限未删除项目：

| 来源 | 判据 |
|---|---|
| (a) | ``projects.created_by == 本人``（本人创建） |
| (b) | ``projects.created_by ∈ 下属``（``users.parent_partner_id == 本人`` 的未删除账号创建） |
| (c) | ``projects.partner_id == 本人``（签字合伙人） |
| (d) | ``working_paper`` / ``wp_index`` 的 ``assigned_to`` / ``reviewer`` 是本人 |
| (e) | ``project_assignments`` 经 ``staff_members.user_id`` 桥接到本人（团队委派） |
| (f) | ``project_users`` 有本人的未删除成员行（与项目门禁同口径） |

(a)~(e) 与参考实现（gt-new-plan ``partner-project-visibility-scope``）一致；(f) 是为了与
``assert_project_permission``（按成员行放行）对齐，避免「能打开却在列表里看不到」。
项目列表、项目树、底稿读写放行、自定义查询等调用方都读这一个函数，避免多处各写一套后漂移。

依赖方向单向：本模块只依赖 ``app.models``，不导入 ``app.deps``（deps 会导入本模块）。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex

__all__ = ["subordinate_ids", "partner_visible_project_ids", "is_partner"]


def is_partner(user: object) -> bool:
    """系统角色是否为 partner（兼容枚举与字符串）。"""
    role = getattr(user, "role", None)
    return str(getattr(role, "value", role) or "") == "partner"


async def subordinate_ids(partner_id: UUID, db: AsyncSession) -> set[UUID]:
    """``parent_partner_id`` 指向该合伙人的全部未删除账号 id（不按角色过滤，每次实时查）。"""
    rows = (
        await db.execute(
            select(User.id).where(
                User.parent_partner_id == partner_id,
                User.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().all()
    return set(rows)


async def partner_visible_project_ids(user: User, db: AsyncSession) -> set[UUID]:
    """合伙人可见项目集（六来源并集）。本函数不判角色，调用方须先确认是 partner。"""
    visible: set[UUID] = set()

    # (a) 本人创建。created_by 为 NULL 的历史项目天然不命中（只对 admin 可见）
    visible.update(
        (
            await db.execute(
                select(Project.id).where(
                    Project.created_by == user.id,
                    Project.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
    )

    # (b) 下属创建；无下属时跳过，避免生成 IN ()
    subs = await subordinate_ids(user.id, db)
    if subs:
        visible.update(
            (
                await db.execute(
                    select(Project.id).where(
                        Project.created_by.in_(subs),
                        Project.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalars().all()
        )

    # (c) 本人为签字合伙人
    visible.update(
        (
            await db.execute(
                select(Project.id).where(
                    Project.partner_id == user.id,
                    Project.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
    )

    # (d) 持有该项目底稿（编制人 / 复核人）；两张表各有一套这两列，都要查
    for model in (WpIndex, WorkingPaper):
        visible.update(
            (
                await db.execute(
                    select(model.project_id)
                    .join(Project, Project.id == model.project_id)
                    .where(
                        or_(model.assigned_to == user.id, model.reviewer == user.id),
                        model.is_deleted == False,  # noqa: E712
                        Project.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalars().all()
        )

    # (e) 团队委派。必须 INNER JOIN：staff_members.user_id 可为 NULL，LEFT JOIN 会泄露
    visible.update(
        (
            await db.execute(
                select(ProjectAssignment.project_id)
                .join(StaffMember, StaffMember.id == ProjectAssignment.staff_id)
                .join(Project, Project.id == ProjectAssignment.project_id)
                .where(
                    StaffMember.user_id == user.id,
                    ProjectAssignment.is_deleted == False,  # noqa: E712
                    StaffMember.is_deleted == False,  # noqa: E712
                    Project.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
    )

    # (f) 本人是项目成员（project_users 未删除行）。项目门禁 assert_project_permission
    #     按成员行放行；不并入这一来源会出现「打得开却在列表里看不到」
    visible.update(
        (
            await db.execute(
                select(ProjectUser.project_id)
                .join(Project, Project.id == ProjectUser.project_id)
                .where(
                    ProjectUser.user_id == user.id,
                    ProjectUser.is_deleted == False,  # noqa: E712
                    Project.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
    )

    return visible
