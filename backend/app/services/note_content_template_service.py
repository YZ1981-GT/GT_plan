"""附注内容模板领域服务：集团根追溯、模板授权和 CRUD 骨架。

spec: disclosure-note-doc-upload-and-batch-fill Phase 1 Task 6~7
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, User
from app.models.note_content_template_models import NoteContentTemplate

logger = logging.getLogger(__name__)

_MAX_DEPTH = 20  # 环路/超深保护


async def resolve_canonical_group_root(
    db: AsyncSession, project_id: UUID
) -> UUID | None:
    """沿 parent_project_id 向上追溯到根项目。

    - standalone（parent_project_id 为空）直接返回自身 ID 作为集团根。
    - 链深度超过 _MAX_DEPTH 或检测到环路时返回 None。
    - 项目不存在/已软删返回 None。
    """
    visited: set[UUID] = set()
    current = project_id
    for _ in range(_MAX_DEPTH):
        if current in visited:
            logger.warning("集团根解析检测到环路：project_id=%s visited=%s", project_id, visited)
            return None
        visited.add(current)
        row = await db.execute(
            sa.select(Project.id, Project.parent_project_id).where(
                Project.id == current, Project.is_deleted == sa.false()
            )
        )
        rec = row.one_or_none()
        if rec is None:
            logger.warning("集团根解析中止：project_id=%s 不存在或已软删", current)
            return None
        if rec.parent_project_id is None:
            return rec.id
        current = rec.parent_project_id
    logger.warning("集团根解析深度超限：project_id=%s depth=%d", project_id, _MAX_DEPTH)
    return None


# ── 角色允许保存/删除 group 模板的白名单 ──────────────────────────────────

_GROUP_MANAGE_SYSTEM_ROLES = {"admin", "partner", "manager"}
_GROUP_MANAGE_PROJECT_ROLES = {"signing_partner", "manager"}


async def can_manage_group_template(
    db: AsyncSession, user: User, canonical_group_root: UUID
) -> bool:
    """判断用户是否有权创建/删除集团级模板。

    系统角色 admin 或在 canonical group root 项目担任 manager/signing_partner。
    """
    if user.role.value in _GROUP_MANAGE_SYSTEM_ROLES:
        return True
    from app.models.staff_models import ProjectAssignment, StaffMember
    role = await db.scalar(
        sa.select(ProjectAssignment.role)
        .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
        .where(
            ProjectAssignment.project_id == canonical_group_root,
            StaffMember.user_id == user.id,
            ProjectAssignment.is_deleted == sa.false(),
            StaffMember.is_deleted == sa.false(),
        )
    )
    return role in _GROUP_MANAGE_PROJECT_ROLES


async def can_view_template(
    db: AsyncSession, user: User, template: NoteContentTemplate, *, viewer_project_id: UUID
) -> bool:
    """判断用户是否可见某附注内容模板。

    - personal：仅 owner_user_id == 当前用户。
    - group：viewer 项目的 canonical group root == 模板的 owner_group_project_id。
    - 不可见时端点统一返回 404，不泄露存在性。
    """
    if template.is_deleted:
        return False
    if template.owner_scope == "personal":
        return template.owner_user_id == user.id
    if template.owner_scope == "group":
        root = await resolve_canonical_group_root(db, viewer_project_id)
        return root is not None and root == template.owner_group_project_id
    return False
