"""项目成员的有效循环范围（spec procedure-trim-generation-delegation-chain 需求 5 / ADR-5）。

用户裁决（2026-10-24）：经理、合伙人、质控、EQCR 默认看本项目全部循环；审计员按团队分配时勾选的循环。

- **主管**：本项目任一有效委派记录（``project_assignments``）的角色属于合伙人 / 签字合伙人 / 项目经理 /
  质控 / EQCR（含中文别名，取自 ``assignment_service.ROLE_MAP`` 映射到合伙人、经理、质控的角色，不另写别名表），
  且当前用户只有一份未删除人员记录、一行未删除项目成员行（与分类器的唯一链路同口径，链路不唯一一律按受限）。
  有效范围 = 全部循环（A~N、S ∪ 本项目底稿索引里出现的循环）。
- **受限**：有效范围 = 全部有效委派记录勾选的循环（``assigned_cycles``）∪ ``project_users.scope_cycles``
  （委派时扩大的循环与手工设置）。没勾选也没扩大 ⇒ 空集，什么都看不到（不按「空 = 全部」）。
- **系统管理员**：与角色分类器一致（admin 不受循环范围限制），按主管返回全部循环。

角色分类器、委派的跨循环校验、``get_user_scope_cycles``（试算表 / 调整 / 附注过滤）都调本模块，一处口径。
纯读，不写库。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ProjectUserRole
from app.models.core import ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WpIndex
from app.services.assignment_service import ROLE_MAP

logger = logging.getLogger(__name__)

#: 团队分配界面可勾选的循环（A~N + S）
STANDARD_CYCLES: frozenset[str] = frozenset("ABCDEFGHIJKLMN") | {"S"}

#: 主管角色：委派角色映射到合伙人 / 经理 / 质控项目角色的全部写法（英文代码 + 中文别名）
SUPERVISOR_ROLES: frozenset[str] = frozenset(
    k.strip().lower() for k, (role, _lv) in ROLE_MAP.items()
    if role in (ProjectUserRole.partner, ProjectUserRole.manager, ProjectUserRole.qc)
)


@dataclass(frozen=True)
class MemberScope:
    is_supervisor: bool
    cycles: frozenset[str]     # 有效范围
    assigned: frozenset[str]   # 团队分配勾选
    expanded: frozenset[str]   # project_users.scope_cycles（扩权 / 手工）
    roles: frozenset[str]      # 有效委派角色（规范化）
    is_member: bool = False    # 本项目有未删除的项目成员行（没有就无从扩大可见范围）
    is_admin: bool = False     # 系统管理员

    def to_payload(self) -> dict:
        """契约 member-scope.schema.json：集合按升序列出。"""
        return {
            "is_supervisor": self.is_supervisor, "cycles": sorted(self.cycles), "assigned": sorted(self.assigned),
            "expanded": sorted(self.expanded), "roles": sorted(self.roles), "is_member": self.is_member,
            "is_admin": self.is_admin,
        }


def normalize_role(role: str | None) -> str:
    return (role or "").strip().lower()


def parse_cycles(raw) -> frozenset[str]:
    """``scope_cycles``（逗号分隔文本）或 ``assigned_cycles``（JSON 数组）→ 循环代号集合。"""
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, (list, tuple, set, frozenset)):
        items = list(raw)
    elif isinstance(raw, dict):
        items = list(raw.get("cycles") or [])
    else:
        return frozenset()
    return frozenset(str(c).strip() for c in items if str(c).strip())


async def project_cycles(db: AsyncSession, project_id: UUID) -> frozenset[str]:
    """本项目全部循环：A~N、S ∪ 底稿索引里出现的循环代号。"""
    rows = await db.execute(
        sa.select(WpIndex.audit_cycle).where(WpIndex.project_id == project_id, WpIndex.audit_cycle.isnot(None))
        .distinct()
    )
    return STANDARD_CYCLES | frozenset(str(r[0]).strip() for r in rows.all() if str(r[0] or "").strip())


async def resolve_member_scope(db: AsyncSession, project_id: UUID, user_id: UUID) -> MemberScope:
    """当前用户在本项目的有效循环范围（见模块说明）。查询失败按受限空集（fail-closed）。"""
    try:
        system_role = (await db.execute(sa.select(User.role).where(User.id == user_id))).scalar_one_or_none()
        staff_ids = list((await db.execute(
            sa.select(StaffMember.id).where(StaffMember.user_id == user_id, StaffMember.is_deleted == sa.false())
        )).scalars().all())
        assignments = (await db.execute(
            sa.select(ProjectAssignment.role, ProjectAssignment.assigned_cycles).where(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.staff_id.in_(staff_ids),
                ProjectAssignment.is_deleted == sa.false(),
            )
        )).all() if staff_ids else []
        member_rows = (await db.execute(
            sa.select(ProjectUser.scope_cycles).where(
                ProjectUser.project_id == project_id,
                ProjectUser.user_id == user_id,
                ProjectUser.is_deleted == sa.false(),
            )
        )).all()
    except Exception as exc:  # noqa: BLE001 — 读不到 ⇒ 受限空集
        logger.warning("有效循环范围查询失败 user=%s project=%s: %s", user_id, project_id, exc)
        return MemberScope(False, frozenset(), frozenset(), frozenset(), frozenset())

    roles = frozenset(normalize_role(r[0]) for r in assignments if normalize_role(r[0]))
    assigned = frozenset().union(*(parse_cycles(r[1]) for r in assignments)) if assignments else frozenset()
    expanded = frozenset().union(*(parse_cycles(r[0]) for r in member_rows)) if member_rows else frozenset()
    is_member = bool(member_rows)
    is_admin = getattr(system_role, "value", system_role) == "admin"
    unique_chain = len(staff_ids) == 1 and len(member_rows) == 1
    if is_admin or (unique_chain and roles & SUPERVISOR_ROLES):
        return MemberScope(
            True, await project_cycles(db, project_id), assigned, expanded, roles, is_member, is_admin
        )
    return MemberScope(False, assigned | expanded, assigned, expanded, roles, is_member, is_admin)
