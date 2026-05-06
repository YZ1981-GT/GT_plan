"""团队委派服务

Phase 9 Task 1.4: 项目团队委派 CRUD + 通知推送
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import PermissionLevel, ProjectUserRole
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.core import Notification, Project
from app.services.notification_types import ASSIGNMENT_CREATED

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ROLE_MAP — 委派角色 → (ProjectUserRole, PermissionLevel) 的单一真源
# ---------------------------------------------------------------------------
# R5 任务 2：将字典抽到模块级，满足跨轮约束 2 的"权限四点同步"显式验证脚本：
#
#     from app.services.assignment_service import ROLE_MAP
#     assert 'eqcr' in ROLE_MAP
#
# 同时保留原有 ``_sync_project_users`` 中的用法，内部直接引用本常量。
# ``ProjectUserRole`` 不新增 ``eqcr`` 枚举（与 design.md "架构决策一览"
# "EQCR 角色挂载复用 ProjectAssignment.role='eqcr'" 对齐），
# 因此 eqcr 在 project_users 层面映射为 partner+review；
# 独立性仍由 ``project_assignments.role='eqcr'`` 在业务层区分。
ROLE_MAP: dict[str, tuple[ProjectUserRole, PermissionLevel]] = {
    "signing_partner": (ProjectUserRole.partner, PermissionLevel.review),
    "partner": (ProjectUserRole.partner, PermissionLevel.review),
    "合伙人": (ProjectUserRole.partner, PermissionLevel.review),
    "manager": (ProjectUserRole.manager, PermissionLevel.review),
    "项目经理": (ProjectUserRole.manager, PermissionLevel.review),
    "qc": (ProjectUserRole.qc, PermissionLevel.review),
    "质控": (ProjectUserRole.qc, PermissionLevel.review),
    "auditor": (ProjectUserRole.auditor, PermissionLevel.edit),
    "审计员": (ProjectUserRole.auditor, PermissionLevel.edit),
    "assistant": (ProjectUserRole.auditor, PermissionLevel.edit),
    "助理": (ProjectUserRole.auditor, PermissionLevel.edit),
    # R5 任务 2：EQCR 独立复核合伙人
    "eqcr": (ProjectUserRole.partner, PermissionLevel.review),
    "独立复核合伙人": (ProjectUserRole.partner, PermissionLevel.review),
}


class AssignmentService:
    """项目团队委派服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_assignments(self, project_id: UUID) -> list[dict]:
        """获取项目的团队委派列表"""
        q = (
            sa.select(
                ProjectAssignment,
                StaffMember.name.label("staff_name"),
                StaffMember.title.label("staff_title"),
                StaffMember.employee_no,
            )
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .where(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.is_deleted == False,  # noqa
            )
            .order_by(ProjectAssignment.assigned_at)
        )
        rows = (await self.db.execute(q)).all()
        results = []
        for row in rows:
            pa = row[0]
            results.append({
                "id": str(pa.id),
                "project_id": str(pa.project_id),
                "staff_id": str(pa.staff_id),
                "role": pa.role,
                "assigned_cycles": pa.assigned_cycles,
                "assigned_at": str(pa.assigned_at) if pa.assigned_at else None,
                "staff_name": row.staff_name,
                "staff_title": row.staff_title,
                "employee_no": row.employee_no,
            })
        return results

    async def save_assignments(
        self,
        project_id: UUID,
        assignments: list[dict],
        assigned_by: UUID | None = None,
    ) -> list[ProjectAssignment]:
        """批量保存委派（先软删除旧的，再插入新的）

        R5 任务 2：在落库前对每一条委派执行 SOD 校验（EQCR 独立性规则），
        任一条冲突则整批拒绝，避免部分落库的一致性问题。
        """
        now = datetime.utcnow()

        # ---- R5: SOD 前置校验（EQCR 独立性） ----
        # 同批次中 staff_id+role 的组合用来模拟"本次将形成的终态"，
        # 避免先删后插的瞬时窗口让规则误判。
        from app.services.sod_guard_service import (
            EqcrIndependenceRule,
            SodViolation,
        )

        rule = EqcrIndependenceRule()
        proposed_roles: list[tuple[UUID, str]] = [
            (a["staff_id"], a["role"]) for a in assignments
        ]
        for staff_id, role in proposed_roles:
            try:
                await rule.check(
                    self.db,
                    project_id=project_id,
                    staff_id=staff_id,
                    new_role=role,
                    proposed_roles=proposed_roles,
                )
            except SodViolation as exc:
                # 冒泡给 router 层转成 403/409
                raise exc

        # 软删除现有委派
        await self.db.execute(
            sa.update(ProjectAssignment)
            .where(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.is_deleted == False,  # noqa
            )
            .values(is_deleted=True, deleted_at=now)
        )

        # 插入新委派
        created = []
        for a in assignments:
            pa = ProjectAssignment(
                project_id=project_id,
                staff_id=a["staff_id"],
                role=a["role"],
                assigned_cycles=a.get("assigned_cycles"),
                assigned_at=now,
                assigned_by=assigned_by,
            )
            self.db.add(pa)
            created.append(pa)

        await self.db.flush()

        # 自动同步 project_users 表（解决委派与权限脱节问题）
        await self._sync_project_users(project_id, created)

        # 发送通知给被委派人员
        await self._send_assignment_notifications(project_id, created)

        # 发布 SSE 事件通知前端
        try:
            from app.services.event_bus import event_bus
            from app.models.audit_platform_schemas import EventPayload, EventType
            await event_bus.publish(EventPayload(
                event_type=EventType.DATA_IMPORTED,  # 复用事件类型，前端按 project_id 过滤
                project_id=project_id,
            ))
        except Exception:
            pass  # SSE 推送失败不阻断主流程

        return created

    async def _send_assignment_notifications(
        self, project_id: UUID, assignments: list[ProjectAssignment]
    ) -> None:
        """给被委派人员发送通知"""
        # 获取项目名称
        proj = (await self.db.execute(
            sa.select(Project.name).where(Project.id == project_id)
        )).scalar_one_or_none()
        project_name = proj or "未知项目"

        for pa in assignments:
            # 查找人员关联的 user_id
            staff = (await self.db.execute(
                sa.select(StaffMember.user_id, StaffMember.name)
                .where(StaffMember.id == pa.staff_id)
            )).one_or_none()

            if staff and staff.user_id:
                role_map = {
                    "signing_partner": "签字合伙人",
                    "manager": "项目经理",
                    "auditor": "审计员",
                    "qc": "质控人员",
                    "eqcr": "独立复核合伙人",  # R5 任务 2
                }
                role_cn = role_map.get(pa.role, pa.role)
                cycles = ", ".join(pa.assigned_cycles) if pa.assigned_cycles else "全部"

                notif = Notification(
                    recipient_id=staff.user_id,
                    message_type=ASSIGNMENT_CREATED,
                    title=f"您已被委派到项目「{project_name}」",
                    content=f"角色：{role_cn}，负责循环：{cycles}。点击前往填报工时：/work-hours",
                    related_object_type="project",
                    related_object_id=project_id,
                )
                self.db.add(notif)

    async def _sync_project_users(
        self, project_id: UUID, assignments: list[ProjectAssignment]
    ) -> None:
        """委派时自动同步 project_users 表，确保 require_project_access 不会 403。

        R5 任务 2：映射表升级到模块级 :data:`ROLE_MAP`（单一真源），
        这里直接引用，不再本地重复定义。
        """
        from app.models.core import ProjectUser

        for pa in assignments:
            staff = (await self.db.execute(
                sa.select(StaffMember.user_id).where(StaffMember.id == pa.staff_id)
            )).scalar()
            if not staff:
                continue

            mapped = ROLE_MAP.get(pa.role, (ProjectUserRole.readonly, PermissionLevel.readonly))

            # upsert: 查找已有记录
            existing = (await self.db.execute(
                sa.select(ProjectUser).where(
                    ProjectUser.project_id == project_id,
                    ProjectUser.user_id == staff,
                    ProjectUser.is_deleted == False,
                )
            )).scalar_one_or_none()

            if existing:
                # 更新角色（取更高权限）
                from app.models.base import PermissionLevel as PL
                PERM_ORDER = {PL.readonly: 0, PL.review: 1, PL.edit: 2}
                if PERM_ORDER.get(mapped[1], 0) > PERM_ORDER.get(existing.permission_level, 0):
                    existing.role = mapped[0]
                    existing.permission_level = mapped[1]
            else:
                pu = ProjectUser(
                    project_id=project_id,
                    user_id=staff,
                    role=mapped[0],
                    permission_level=mapped[1],
                )
                self.db.add(pu)

        await self.db.flush()

    async def get_my_assignments(self, user_id: UUID) -> list[dict]:
        """获取当前用户被委派的项目列表"""
        q = (
            sa.select(
                ProjectAssignment,
                Project.name.label("project_name"),
                Project.client_name,
                Project.status.label("project_status"),
            )
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .join(Project, ProjectAssignment.project_id == Project.id)
            .where(
                StaffMember.user_id == user_id,
                ProjectAssignment.is_deleted == False,  # noqa
                Project.is_deleted == False,  # noqa
            )
            .order_by(ProjectAssignment.assigned_at.desc())
        )
        rows = (await self.db.execute(q)).all()
        return [
            {
                "project_id": str(row[0].project_id),
                "project_name": row.project_name,
                "client_name": row.client_name,
                "project_status": row.project_status,
                "role": row[0].role,
                "assigned_cycles": row[0].assigned_cycles,
                "assigned_at": str(row[0].assigned_at) if row[0].assigned_at else None,
            }
            for row in rows
        ]
